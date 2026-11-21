"""The input/output contract of a desktop flow and the check against the cloud flow action that runs it."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

RUN_ACTION_OPERATION = "RunUIFlow_V2"  # "Run a flow built with Power Automate for desktop" (connectors reference)
INPUT_LIMIT_BYTES = 2 * 1024 * 1024    # "The limit of the input size for a desktop flow is 2 MB"


@dataclass
class Finding:
    level: str
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.where}: {self.message}"


def load_contract(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _iter_actions(actions: dict):
    for name, a in actions.items():
        yield name, a
        for sub in (a.get("actions") or {}, (a.get("else") or {}).get("actions") or {}):
            yield from _iter_actions(sub)
        for case in (a.get("cases") or {}).values():
            yield from _iter_actions(case.get("actions") or {})
        yield from _iter_actions((a.get("default") or {}).get("actions") or {})


def run_actions(flow: dict) -> dict:
    defn = flow["properties"]["definition"]
    def op(a):
        inputs = a.get("inputs")
        host = inputs.get("host") if isinstance(inputs, dict) else None
        return host.get("operationId") if isinstance(host, dict) else None

    return {n: a for n, a in _iter_actions(defn["actions"]) if op(a) == RUN_ACTION_OPERATION}


def check_cloud_flow(flow: dict, contract: dict) -> list[Finding]:
    out: list[Finding] = []
    declared_in = {i["name"]: i for i in contract["inputs"]}
    declared_out = {o["name"] for o in contract["outputs"]}
    runs = run_actions(flow)
    if not runs:
        return [Finding("error", "PAD101", "cloud flow", f"no '{RUN_ACTION_OPERATION}' action found")]
    text = json.dumps(flow)
    for name, action in runs.items():
        params = action["inputs"].get("parameters", {})
        passed = {k[len("item/"):] for k in params if k.startswith("item/")}
        for missing in sorted(n for n, i in declared_in.items() if not i.get("optional") and n not in passed):
            out.append(Finding("error", "PAD102", name, f"required input '{missing}' of the desktop flow is not passed"))
        for extra in sorted(passed - set(declared_in)):
            out.append(Finding("error", "PAD103", name, f"passes '{extra}', which the desktop flow does not declare"))
        mode = params.get("runMode")
        if mode not in ("attended", "unattended"):
            out.append(Finding("error", "PAD104", name, f"runMode is {mode!r}; the action takes attended or unattended"))
        if "uiFlowId" not in params:
            out.append(Finding("error", "PAD105", name, "uiFlowId is missing"))
        if not action.get("limit", {}).get("timeout"):
            out.append(Finding("warning", "PAD106", name, "no timeout on the action: a stuck desktop session would wait for the platform default"))
        used = set(re.findall(rf"outputs\('{re.escape(name)}'\)\?\['body/([A-Za-z0-9_]+)'\]", text))
        for u in sorted(used - declared_out):
            out.append(Finding("error", "PAD107", name, f"reads output '{u}', which the desktop flow does not declare"))
        if not _has_failure_path(flow, name):
            out.append(Finding("warning", "PAD108", name, "nothing runs when the desktop flow fails or times out"))
    return out


def _has_failure_path(flow: dict, run_name: str) -> bool:
    """A scope (or action) that runs after the failure of the scope containing the desktop flow action."""
    actions = flow["properties"]["definition"]["actions"]
    holder = next((n for n, a in actions.items() if run_name in (a.get("actions") or {})), run_name)
    for a in actions.values():
        ra = a.get("runAfter") or {}
        if holder in ra and set(ra[holder]) & {"Failed", "TimedOut"}:
            return True
    return False


def check_input_size(inputs: dict) -> list[Finding]:
    size = len(json.dumps(inputs).encode("utf-8"))
    if size > INPUT_LIMIT_BYTES:
        return [Finding("error", "PAD109", "inputs", f"{size} bytes; the limit for desktop flow input is 2 MB")]
    return []
