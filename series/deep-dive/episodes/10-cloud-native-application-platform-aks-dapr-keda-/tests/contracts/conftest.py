import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def arm() -> dict:
    """The REAL compiled Bicep: `bicep build`, not a re-implementation."""
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def outputs() -> dict:
    """Dummy deployment outputs, shaped like `az deployment group show --query properties.outputs`."""
    vals = {
        "appClientId": "11111111-1111-1111-1111-111111111111",
        "kedaClientId": "22222222-2222-2222-2222-222222222222",
        "serviceBusFqdn": "sb-mgl10-abc123.servicebus.windows.net",
        "serviceBusNamespace": "sb-mgl10-abc123",
    }
    return {k: {"type": "String", "value": v} for k, v in vals.items()}


@pytest.fixture(scope="session")
def rendered(tmp_path_factory, outputs) -> dict:
    """All manifests rendered by the real script, parsed: {filename: [documents]}."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import render_manifests

    out = tmp_path_factory.mktemp("rendered")
    f = tmp_path_factory.mktemp("o") / "outputs.json"
    f.write_text(json.dumps(outputs))
    assert render_manifests.main(["--outputs", str(f), "--image", "acrmgl10abc123.azurecr.io/finance-worker:1", "--out", str(out)]) == 0
    return {p.name: list(yaml.safe_load_all(p.read_text())) for p in sorted(out.glob("*.yaml"))}


def resources(arm: dict, rtype: str) -> list[dict]:
    return [r for r in arm["resources"] if r["type"] == rtype]


def program_constants() -> dict:
    src = (ROOT / "src" / "FinanceReview.Worker" / "Program.cs").read_text()
    return dict(re.findall(r'const string (\w+) = "([^"]+)";', src))


# ---- a tiny evaluator for the ARM expressions the compiled Bicep uses in names and subjects -------------------------
def _split_args(s: str) -> list[str]:
    args, depth, cur, q = [], 0, "", False
    for ch in s:
        if ch == "'":
            q = not q
        if not q and ch == "(":
            depth += 1
        if not q and ch == ")":
            depth -= 1
        if not q and depth == 0 and ch == ",":
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def arm_eval(expr, arm: dict):
    """Evaluate `[variables('x')]`, `[parameters('x')]`, `[format('{0}/{1}', ...)]` and string literals. Anything else raises."""
    if not isinstance(expr, str):
        return expr
    e = expr.strip()
    if e.startswith("[[") or not (e.startswith("[") and e.endswith("]")):
        return e
    return _ev(e[1:-1].strip(), arm)


def _ev(e: str, arm: dict):
    if e.startswith("'") and e.endswith("'"):
        return e[1:-1]
    if re.fullmatch(r"-?\d+", e):
        return int(e)
    if e == "subscription().id":
        return "/subscriptions/00000000-0000-0000-0000-000000000000"
    if e == "resourceGroup().id":
        return "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test"
    m = re.fullmatch(r"(\w+)\((.*)\)", e, re.S)
    if not m:
        raise ValueError(f"unsupported ARM expression: {e}")
    fn, inner = m.group(1), m.group(2)
    args = [_ev(a, arm) for a in _split_args(inner)]
    if fn == "variables":
        return arm_eval(arm["variables"][args[0]], arm)
    if fn == "parameters":
        return arm["parameters"][args[0]]["defaultValue"]
    if fn == "uniqueString":
        return "abc123"  # the real value is a hash; the contracts only need a stable stand-in
    if fn == "take":
        return str(args[0])[: int(args[1])]
    if fn == "format":
        out = args[0]
        for i, a in enumerate(args[1:]):
            out = out.replace("{%d}" % i, str(a))
        return out
    raise ValueError(f"unsupported ARM function {fn}: {e}")
