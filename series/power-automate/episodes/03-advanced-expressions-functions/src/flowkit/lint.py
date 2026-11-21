"""Static checks for a cloud flow definition (the JSON inside a solution's Workflows folder).

Every rule here comes from Microsoft Learn (limits page, variables page, trigger conditions,
connection references) or from the workflow definition schema itself. None of it needs a tenant.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import expr as wdl

RUN_AFTER_STATUSES = {"Succeeded", "Failed", "Skipped", "TimedOut"}
CONTAINER_TYPES = {"If", "Switch", "Scope", "Foreach", "Until"}
MAX_ACTIONS = 500          # "Actions per workflow"
MAX_NESTING = 8            # "Allowed nesting depth for actions"
MAX_VARIABLES = 250        # "Variables per workflow"
MAX_ASYNC_DAYS = 30        # run duration; asynchronous timeouts "configurable up to 30 days"
MAX_FOREACH_CONCURRENCY = 50
MAX_EXPRESSION_CHARS = 8192  # "Characters per expression"
CONNECTOR_TYPES = {"OpenApiConnection", "OpenApiConnectionWebhook", "OpenApiConnectionNotification"}


@dataclass
class Finding:
    level: str  # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


_DURATION_RE = re.compile(
    r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$"
)


def iso_duration_seconds(text: str) -> float:
    """Parse the ISO 8601 durations flows use (PnDTnHnMnS). Raises ValueError otherwise."""
    m = _DURATION_RE.match(text or "")
    if not m or text in ("P", "PT") or text.endswith("T"):
        raise ValueError(f"{text!r} is not an ISO 8601 duration like PT10M or P3D")
    d, h, mi, s = (float(m.group(k) or 0) for k in "dhms")
    return d * 86400 + h * 3600 + mi * 60 + s


def load_flow(path: str | Path) -> dict:
    """Load a flow file. Accepts the solution format ({"properties": {...}}) or a bare definition."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return data


def definition_of(flow: dict) -> dict:
    if "properties" in flow and "definition" in flow["properties"]:
        return flow["properties"]["definition"]
    if "triggers" in flow or "actions" in flow:
        return flow
    raise ValueError("Not a flow: expected properties.definition or a definition with triggers/actions")


def connection_refs_of(flow: dict) -> dict:
    return flow.get("properties", {}).get("connectionReferences", {}) if "properties" in flow else {}


def child_scopes(action: dict) -> list[tuple[str, dict]]:
    """(label, actions-dict) for every nested block of a container action."""
    t = action.get("type")
    out = []
    if t in ("Scope", "Foreach", "Until"):
        out.append(("actions", action.get("actions", {})))
    elif t == "If":
        out.append(("actions", action.get("actions", {})))
        out.append(("else", action.get("else", {}).get("actions", {})))
    elif t == "Switch":
        for case_name, case in action.get("cases", {}).items():
            out.append((f"cases.{case_name}", case.get("actions", {})))
        out.append(("default", action.get("default", {}).get("actions", {})))
    return out


def iter_actions(actions: dict, depth: int = 1, loops: tuple = (), path: str = "actions"):
    """Yield (name, action, depth, enclosing_foreach_names, scope_dict, path) recursively."""
    for name, action in actions.items():
        yield name, action, depth, loops, actions, f"{path}.{name}"
        inner_loops = loops + ((name,) if action.get("type") == "Foreach" else ())
        for label, scope in child_scopes(action):
            yield from iter_actions(scope, depth + 1, inner_loops, f"{path}.{name}.{label}")


def _expression_sources(action: dict) -> list:
    """The parts of an action that can hold expressions."""
    srcs = [action.get("inputs")]
    t = action.get("type")
    if t in ("If", "Switch"):
        srcs.append(action.get("expression"))
    if t == "Foreach":
        srcs.append(action.get("foreach"))
    if t == "Until":
        srcs.append(action.get("expression"))
    return srcs


def _condition_strings(expression) -> list:
    """Expressions inside an If condition: a string, or the designer's object form."""
    return ["@" + e for e in wdl.expressions_in(expression)]


def _find_cycle(scope: dict) -> list[str] | None:
    graph = {n: [d for d in (a.get("runAfter") or {}) if d in scope] for n, a in scope.items()}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n):
        state[n] = 1
        stack.append(n)
        for d in graph[n]:
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in state:
                found = visit(d)
                if found:
                    return found
        stack.pop()
        state[n] = 2
        return None

    for n in graph:
        if n not in state:
            found = visit(n)
            if found:
                return found
    return None


def lint(flow: dict) -> list[Finding]:
    findings: list[Finding] = []
    err = lambda where, msg: findings.append(Finding("error", where, msg))
    warn = lambda where, msg: findings.append(Finding("warning", where, msg))

    try:
        d = definition_of(flow)
    except ValueError as e:
        return [Finding("error", "flow", str(e))]

    if "workflowdefinition.json" not in d.get("$schema", ""):
        warn("definition", "missing the Logic Apps workflow definition $schema")

    triggers = d.get("triggers", {})
    if len(triggers) != 1:
        err("triggers", f"a cloud flow has exactly one trigger, found {len(triggers)}")

    conn_refs = connection_refs_of(flow)
    actions = d.get("actions", {})
    all_actions = list(iter_actions(actions))
    names = [n for n, *_ in all_actions]
    name_set = set(names)

    # --- limits from "Limits of automated, scheduled, and instant flows"
    if len(all_actions) > MAX_ACTIONS:
        err("actions", f"{len(all_actions)} actions; the limit is {MAX_ACTIONS} per workflow")
    for name in {n for n in names if names.count(n) > 1}:
        err(f"actions.{name}", "action names must be unique across the whole flow")

    declared_vars: dict[str, str] = {}
    for name, action, depth, loops, scope, where in all_actions:
        t = action.get("type")
        if depth > MAX_NESTING:
            err(where, f"nesting depth {depth} exceeds the limit of {MAX_NESTING}; use a child flow")
        if t == "InitializeVariable":
            if depth != 1:
                err(where, "Initialize variable is only allowed at the top level, not inside scopes, conditions or loops")
            for v in action.get("inputs", {}).get("variables", []):
                vtype = str(v.get("type", "")).lower()
                if vtype not in {"string", "integer", "float", "boolean", "array", "object"}:
                    err(where, f"variable {v.get('name')!r} has unknown type {v.get('type')!r}")
                if v.get("name") in declared_vars:
                    err(where, f"variable {v.get('name')!r} is initialized twice")
                declared_vars[v.get("name")] = vtype
    if len(declared_vars) > MAX_VARIABLES:
        err("actions", f"{len(declared_vars)} variables; the limit is {MAX_VARIABLES}")

    # --- triggers
    for tname, trig in triggers.items():
        where = f"triggers.{tname}"
        for i, cond in enumerate(trig.get("conditions", [])):
            text = cond.get("expression", "")
            if not text.startswith("@"):
                err(f"{where}.conditions[{i}]", "every trigger condition must start with '@'")
            _check_expressions([text], f"{where}.conditions[{i}]", (), name_set, declared_vars, all_actions, err, in_trigger=True)
        rec = trig.get("recurrence")
        if rec:
            unit = {"Second": 1, "Minute": 60, "Hour": 3600, "Day": 86400, "Week": 604800, "Month": 2592000}
            seconds = unit.get(rec.get("frequency"), 0) * int(rec.get("interval", 1))
            if seconds and seconds < 60:
                err(where, "the minimum recurrence interval is 60 seconds")
            if seconds > 500 * 86400:
                err(where, "the maximum recurrence interval is 500 days")
        if trig.get("type") in CONNECTOR_TYPES:
            _check_connection(trig, where, conn_refs, err, warn)

    # --- actions
    for name, action, depth, loops, scope, where in all_actions:
        t = action.get("type")
        run_after = action.get("runAfter") or {}
        for dep, statuses in run_after.items():
            if dep not in scope:
                err(where, f"runAfter refers to {dep!r}, which isn't an action in the same scope")
            bad = set(statuses) - RUN_AFTER_STATUSES
            if bad:
                err(where, f"runAfter status {sorted(bad)} isn't one of {sorted(RUN_AFTER_STATUSES)}")
            if not statuses:
                err(where, f"runAfter {dep!r} lists no statuses")
        if t in CONNECTOR_TYPES:
            _check_connection(action, where, conn_refs, err, warn)
        timeout = (action.get("limit") or {}).get("timeout")
        if timeout is not None:
            try:
                secs = iso_duration_seconds(timeout)
                if secs > MAX_ASYNC_DAYS * 86400:
                    err(where, f"timeout {timeout} is longer than the 30-day run duration limit")
            except ValueError as e:
                err(where, str(e))
        if t == "Foreach":
            rep = (action.get("runtimeConfiguration") or {}).get("concurrency", {}).get("repetitions")
            if rep is not None and not (1 <= int(rep) <= MAX_FOREACH_CONCURRENCY):
                err(where, f"Apply to each concurrency must be 1-{MAX_FOREACH_CONCURRENCY}, got {rep}")
        if t == "SetVariable":
            vname = action.get("inputs", {}).get("name")
            if vname not in declared_vars:
                err(where, f"Set variable uses {vname!r}, which no Initialize variable declares")
        if t == "If":
            texts = _condition_strings(action.get("expression"))
            _check_expressions(texts, where, loops, name_set, declared_vars, all_actions, err)
            srcs = [action.get("inputs")]
        else:
            srcs = _expression_sources(action)
        texts = []
        for s in srcs:
            texts.extend("@" + e for e in wdl.expressions_in(s))
        _check_expressions(texts, where, loops, name_set, declared_vars, all_actions, err,
                           own_loop=name if t == "Foreach" else None)

    # --- graph shape per scope
    scopes = [("actions", actions)] + [
        (f"{w}.{label}", sc) for _, a, _, _, _, w in all_actions for label, sc in child_scopes(a)
    ]
    for where, scope in scopes:
        if not scope:
            continue
        if not any(not (a.get("runAfter") or {}) for a in scope.values()):
            err(where, "no action in this scope starts first (every action has a runAfter)")
        cycle = _find_cycle(scope)
        if cycle:
            err(where, "runAfter cycle: " + " -> ".join(cycle))
        for f in skipped_leaf_findings(scope, where):
            findings.append(f)
    findings.extend(approval_findings(all_actions))
    return findings


APPROVAL_WAIT_OPS = {"StartAndWaitForAnApproval", "WaitForAnApproval"}
# Learn (Approvals connector): valid responses to a Basic approval are "Approve" and "Reject", case-sensitive.
WRONG_OUTCOMES = {"approved", "rejected"}


def approval_findings(all_actions) -> list[Finding]:
    """Approval-specific checks: explicit timeouts, and outcome values compared with the right strings."""
    out: list[Finding] = []
    def op_id(a):
        inputs = a.get("inputs")
        return (inputs.get("host") or {}).get("operationId") if isinstance(inputs, dict) else None

    approvals = [(n, a, w) for n, a, _, _, _, w in all_actions if op_id(a) in APPROVAL_WAIT_OPS]
    if not approvals:
        return out
    for name, action, where in approvals:
        if not (action.get("limit") or {}).get("timeout"):
            out.append(Finding("warning", where,
                               "approval without a timeout waits until the 30-day run limit; set Settings > Timeout"))
        handlers = [a for n, a, _, _, scope, _ in all_actions
                    if name in (a.get("runAfter") or {}) and "TimedOut" in a["runAfter"][name]]
        if (action.get("limit") or {}).get("timeout") and not handlers:
            out.append(Finding("warning", where, "approval has a timeout but nothing runs after it 'has timed out'"))
    for name, action, _, _, _, where in all_actions:
        if action.get("type") == "Switch":
            for case_name, case in action.get("cases", {}).items():
                if isinstance(case.get("case"), str) and case["case"].lower() in WRONG_OUTCOMES:
                    out.append(Finding("warning", f"{where}.cases.{case_name}",
                                       f"case {case['case']!r}: approval outcomes are 'Approve' and 'Reject' (case-sensitive)"))
        sources = [action.get("inputs"), action.get("expression")]
        for text in (e for src in sources for e in wdl.expressions_in(src)):
            try:
                tree = wdl.parse(text)
            except wdl.ExpressionError:
                continue
            for node in wdl.walk(tree):
                if isinstance(node, wdl.Call) and node.name.lower() == "equals":
                    for arg in node.args:
                        if isinstance(arg, wdl.Lit) and isinstance(arg.value, str) and arg.value.lower() in WRONG_OUTCOMES:
                            out.append(Finding("warning", where, f"compares with {arg.value!r}: approval outcomes are 'Approve' and 'Reject'"))
        expression = action.get("expression")
        if isinstance(expression, dict):
            for literal in _literals(expression):
                if literal.lower() in WRONG_OUTCOMES:
                    out.append(Finding("warning", where, f"condition compares with {literal!r}: approval outcomes are 'Approve' and 'Reject'"))
    return out


def _literals(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _literals(v)
    elif isinstance(node, list):
        for v in node:
            yield from _literals(v)
    elif isinstance(node, str) and not node.startswith("@"):
        yield node


def skipped_leaf_findings(scope: dict, where: str) -> list[Finding]:
    """A handled failure can still fail the scope.

    Learn ("Handle workflow errors and exceptions"): a branch that ends with a Skipped action takes the
    status of that action's predecessor, and if any branch ends in failure the scope or run is Failed.
    So if P times out and H handles it, a sibling leaf L that only runs after P *succeeded* is skipped,
    and its branch still ends in failure. Join the branches with an action that runs after both.
    """
    out = []
    has_successor = {d for a in scope.values() for d in (a.get("runAfter") or {})}
    for h_name, h in scope.items():
        for p_name, statuses in (h.get("runAfter") or {}).items():
            handled = set(statuses) & {"Failed", "TimedOut"}
            if not handled or p_name not in scope:
                continue
            for l_name, leaf in scope.items():
                if l_name in has_successor or l_name == h_name:
                    continue
                l_statuses = set((leaf.get("runAfter") or {}).get(p_name, []))
                if l_statuses and not handled <= l_statuses:
                    out.append(Finding("warning", f"{where}.{l_name}",
                        f"when {p_name!r} ends {'/'.join(sorted(handled))}, {l_name!r} is skipped and, as the last "
                        f"action of its branch, marks the scope Failed even though {h_name!r} handles it; "
                        f"add an action after both that runs on Succeeded and Skipped"))
    return out


def _check_connection(op: dict, where: str, conn_refs: dict, err, warn):
    host = (op.get("inputs") or {}).get("host", {})
    cname = host.get("connectionName")
    if not cname:
        err(where, "connector operation has no host.connectionName")
        return
    if cname not in conn_refs:
        err(where, f"connectionName {cname!r} isn't declared in properties.connectionReferences")
        return
    ref = conn_refs[cname]
    if not (ref.get("connection") or {}).get("connectionReferenceLogicalName"):
        warn(where, f"{cname!r} isn't bound to a connection reference (not solution-aware)")
    api = (ref.get("api") or {}).get("name")
    if api and host.get("apiId") and not host["apiId"].endswith("/" + api):
        err(where, f"host.apiId {host['apiId']!r} doesn't match the connection's api {api!r}")


_ACTION_FNS = {"body", "outputs", "actions", "result"}


_KNOWN = None


def _check_expressions(texts, where, loops, names, declared_vars, all_actions, err, own_loop=None, in_trigger=False):
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = wdl.known_functions()
    for text in texts:
        if not isinstance(text, str) or not text.startswith("@"):
            continue
        if len(text) - 1 > MAX_EXPRESSION_CHARS:
            err(where, f"expression is {len(text) - 1} characters; the limit is {MAX_EXPRESSION_CHARS} per expression")
        try:
            tree = wdl.parse(text[1:])
        except wdl.ExpressionError as e:
            err(where, f"expression doesn't parse: {e}")
            continue
        for node in wdl.walk(tree):
            if isinstance(node, wdl.Call) and node.name.lower() not in _KNOWN:
                err(where, f"{node.name}() isn't a function flowkit knows (typo, or not implemented in this harness)")
            if not isinstance(node, wdl.Call) or not node.args:
                continue
            fn = node.name.lower()
            arg = node.args[0].value if isinstance(node.args[0], wdl.Lit) else None
            if not isinstance(arg, str):
                continue
            if fn in _ACTION_FNS:
                if in_trigger:
                    err(where, f"{node.name}('{arg}') can't be used in a trigger: actions haven't run yet")
                elif arg not in names:
                    err(where, f"{node.name}('{arg}') refers to an action that doesn't exist")
            elif fn == "items":
                if arg not in loops and arg != own_loop:
                    err(where, f"items('{arg}') is used outside the loop '{arg}'")
            elif fn == "variables":
                if in_trigger:
                    err(where, "variables() can't be used in a trigger condition")
                elif arg not in declared_vars:
                    err(where, f"variables('{arg}') isn't initialized by any Initialize variable action")


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="flowkit lint", description="Lint cloud flow definitions")
    p.add_argument("files", nargs="+")
    a = p.parse_args(argv)
    errors = 0
    for f in a.files:
        results = lint(load_flow(f))
        for r in results:
            print(f"{f}: {r}")
        errors += sum(r.level == "error" for r in results)
        if not results:
            print(f"{f}: OK")
    return 1 if errors else 0
