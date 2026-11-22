"""The Deneb spec (src/deneb/target-bullet.vl.json): Deneb's documented data contract, checked statically, and the
spec compiled and run with the Vega-Lite and Vega versions Deneb 2.0.0 bundles (needs `npm ci` in src/deneb)."""
import json
import shutil
import subprocess

import pytest

from conftest import SRC

DENEB = SRC / "deneb"
SPEC = json.loads((DENEB / "target-bullet.vl.json").read_text(encoding="utf-8"))
VALUES_WELL = {"Category", "Sales Amount", "Sales PY"}   # display names of Product[Category] and the two measures


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_spec_follows_denebs_data_contract():
    assert SPEC["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json"      # Deneb 2.0.0 bundles Vega-Lite 6.4.3
    assert SPEC["data"] == {"name": "dataset"}                                         # Deneb binds the Values well to "dataset"
    computed = {t["as"] for t in SPEC["transform"]}
    fields = {n["field"] for n in walk(SPEC) if isinstance(n.get("field"), str)}
    assert fields <= VALUES_WELL | computed, fields - VALUES_WELL - computed
    # Deneb replaces . [ ] \ and " in field names with _: keep names that pass through unchanged
    assert not any(c in f for f in VALUES_WELL for c in '.[]\\"')


def test_no_remote_data_and_no_hard_coded_size():
    text = json.dumps(SPEC)
    assert '"url"' not in text                       # the AppSource build blocks remote data; we need none
    assert "width" not in SPEC and "height" not in SPEC   # Deneb sizes the view to the visual container


def test_same_bands_as_the_typescript_visual():
    # model.ts: variance = (actual - target) / |target|; > tol above, < -tol below, else near; markers ▲ ▼ ●
    calc = " ".join(t["calculate"] for t in SPEC["transform"])
    for s in ("abs(datum['Sales PY'])", "> tolerance", "< -tolerance", "'▲'", "'▼'", "'●'"):
        assert s in calc, s
    assert SPEC["params"] == [{"name": "tolerance", "value": 0.05}]


def run(*extra):
    if not (DENEB / "node_modules" / "vega-lite").exists() or not shutil.which("node"):
        pytest.skip("run `npm ci --no-audit --no-fund` in src/deneb first (vega 6.4.0, vega-lite 6.4.3)")
    r = subprocess.run(["node", "check-spec.mjs", "target-bullet.vl.json", *extra], cwd=DENEB, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_compiles_without_warnings_and_matches_the_expected_2025_rows():
    out = run()
    assert (out["vegaLite"], out["vega"], out["marks"]) == ("6.4.3", "6.4.0", 3)
    rows = {r["Category"]: (r["Band"], r["Label"]) for r in out["rows"]}
    assert rows == {"Accessories": ("above", "▲ +8.4%"), "Bikes": ("above", "▲ +9.0%"), "Clothing": ("near", "● −3.0%")}


def test_tighter_tolerance_and_a_blank_prior_year(tmp_path):
    assert {r["Category"]: r["Band"] for r in run("--tolerance", "0.02")["rows"]}["Clothing"] == "below"
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([{"Category": "Bikes", "Sales Amount": 716095.45, "Sales PY": None}]), encoding="utf-8")
    assert run("--rows", str(rows))["rows"] == [{"Category": "Bikes", "Variance": None, "Band": "noTarget", "Label": "–"}]
