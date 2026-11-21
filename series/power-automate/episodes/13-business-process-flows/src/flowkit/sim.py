"""Dry-run a cloud flow definition locally, with mocked connector calls.

This is a *test harness*, not the Power Automate engine. It walks the definition the way the
engine documents it (runAfter statuses, conditions, switch, scopes, loops, variables, terminate)
and calls your mocks instead of SharePoint, Outlook or Approvals. Use it to prove which branch
runs for which input before you save the flow; then confirm in the real run history.

Run and scope status follow the rule documented in "Handle workflow errors and exceptions in
Azure Logic Apps": every branch is judged by the action it ends with; a branch that ends with a
Skipped action takes the status of that action's predecessor; if any branch ends in failure, the
scope (or the whole run) is Failed. Terminate overrides everything.
"""
from __future__ import annotations

import json

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import copy
import time

from . import expr as wdl
from .httpcall import HttpCallError, HttpClient
from .lint import child_scopes, definition_of, iso_duration_seconds

CONNECTOR_TYPES = {"OpenApiConnection", "OpenApiConnectionWebhook", "ApiConnection",
                   "ApiConnectionWebhook", "Http", "HttpWebhook", "Workflow"}
FAILED_STATUSES = {"Failed", "TimedOut", "Cancelled"}


class SimulationError(Exception):
    """The definition can't be simulated (missing mock, unsupported action type...)."""


class _Terminate(Exception):
    def __init__(self, status: str, error: dict | None):
        self.status, self.error = status, error


@dataclass
class ActionResult:
    status: str
    inputs: Any = None
    outputs: Any = None
    error: str | None = None
    attempts: list = field(default_factory=list)   # HTTP: one entry per request sent (retries included)
    iterations: int | None = None                  # Until: number of iterations run


SECURED = "<secured: hidden in run history>"


@dataclass
class RunResult:
    status: str                       # Succeeded | Failed | Cancelled | Skipped (trigger condition false)
    actions: dict[str, ActionResult] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    terminate_error: dict | None = None
    order: list[str] = field(default_factory=list)
    history: list = field(default_factory=list)   # (name, ActionResult) for every action run, loop iterations included
    executions: int = 0               # action runs, loop iterations included (each one is a Power Platform request)

    def status_of(self, name: str) -> str:
        return self.actions[name].status if name in self.actions else "NotRun"

    def ran(self, name: str) -> bool:
        return self.status_of(name) not in ("Skipped", "NotRun")


Mock = dict | Callable[[Any], dict]


class Simulator:
    def __init__(self, flow: dict, mocks: dict[str, Mock] | None = None, now: datetime | None = None,
                 parameters: dict | None = None, sleep: Callable[[float], None] | None = None,
                 allow_hosts=("127.0.0.1", "localhost")):
        self.definition = definition_of(flow)
        self.mocks = mocks or {}
        self.http = HttpClient(sleep or time.sleep, allow_hosts)
        self.now = now or datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
        defaults = {k: v.get("defaultValue") for k, v in self.definition.get("parameters", {}).items()}
        self.parameters = {**defaults, **(parameters or {})}

    # ------------------------------------------------------------------ public
    def run(self, trigger_body: Any = None, trigger_outputs: Any = None) -> RunResult:
        outputs = trigger_outputs if trigger_outputs is not None else {"headers": {}, "body": trigger_body}
        self.result = RunResult(status="Running")
        self.ctx = wdl.Context(trigger_outputs=outputs, actions={}, variables=self.result.variables,
                               parameters=self.parameters, now=self.now,
                               workflow={"name": "simulated", "run": {"name": "local-run"}})
        (tname, trigger), = self.definition["triggers"].items()
        for cond in trigger.get("conditions", []):
            if wdl.evaluate(cond["expression"], self.ctx) is not True:
                self.result.status = "Skipped"  # the flow isn't triggered; no run in the history
                return self.result
        try:
            status = self._run_scope(self.definition.get("actions", {}))
            self.result.status = status
        except _Terminate as t:
            self.result.status = t.status
            self.result.terminate_error = t.error
        return self.result

    # ------------------------------------------------------------------ engine
    def _record(self, name: str, res: ActionResult):
        self.result.history.append((name, res))
        self.result.actions[name] = res
        self.result.order.append(name)
        self.ctx.actions[name] = {"status": res.status, "outputs": res.outputs, "inputs": res.inputs}

    def _skip_all(self, actions: dict):
        for name, action in actions.items():
            self._record(name, ActionResult("Skipped"))
            for _, scope in child_scopes(action):
                self._skip_all(scope)

    def _run_scope(self, actions: dict) -> str:
        done: dict[str, str] = {}
        pending = list(actions)  # definition order breaks ties, like the designer's top-to-bottom
        while pending:
            ready = [n for n in pending if all(d in done for d in (actions[n].get("runAfter") or {}))]
            if not ready:
                raise SimulationError(f"runAfter can't be satisfied for {pending} (cycle or missing action)")
            name = ready[0]
            pending.remove(name)
            action = actions[name]
            run_after = action.get("runAfter") or {}
            if all(done[d] in statuses for d, statuses in run_after.items()):
                done[name] = self._execute(name, action)
            else:
                self._record(name, ActionResult("Skipped"))
                for _, scope in child_scopes(action):
                    self._skip_all(scope)
                done[name] = "Skipped"
        return scope_status(actions, done)

    def _execute(self, name: str, action: dict) -> str:
        self.result.executions += 1
        t = action.get("type")
        try:
            handler = getattr(self, f"_do_{t}", None)
            if t == "Http" and name in self.mocks:
                handler = None  # a mocked HTTP action behaves like any mocked connector
            if handler:
                return self._secure(name, action, handler(name, action))
            if t in CONNECTOR_TYPES:
                return self._secure(name, action, self._do_connector(name, action))
            raise SimulationError(f"Action type {t!r} ({name}) isn't supported by the simulator")
        except wdl.ExpressionError as e:
            # The engine fails the action with InvalidTemplate when an expression can't be evaluated.
            self._record(name, ActionResult("Failed", error=f"InvalidTemplate: {e}"))
            return "Failed"

    # --- data operations
    def _do_Compose(self, name, action):
        value = wdl.evaluate_value(action.get("inputs"), self.ctx)
        self._record(name, ActionResult("Succeeded", inputs=value, outputs=value))
        return "Succeeded"

    def _do_ParseJson(self, name, action):
        """Parse JSON: returns the content (a JSON string is parsed first). The schema is not enforced here."""
        inputs = wdl.evaluate_value(action["inputs"], self.ctx)
        content = inputs["content"]
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError as e:
                self._record(name, ActionResult("Failed", inputs=inputs, error=f"InvalidTemplate: not JSON: {e}"))
                return "Failed"
        self._record(name, ActionResult("Succeeded", inputs=inputs, outputs=content))
        return "Succeeded"

    def _do_InitializeVariable(self, name, action):
        inputs = wdl.evaluate_value(action["inputs"], self.ctx)
        for v in inputs["variables"]:
            self.ctx.variables[v["name"]] = _coerce(v["type"], v.get("value"), v["name"])
        self._record(name, ActionResult("Succeeded", inputs=inputs))
        return "Succeeded"

    def _do_SetVariable(self, name, action):
        inputs = wdl.evaluate_value(action["inputs"], self.ctx)
        vname = inputs["name"]
        if vname not in self.ctx.variables:
            raise wdl.ExpressionError(f"variable {vname!r} isn't initialized")
        current = self.ctx.variables[vname]
        self.ctx.variables[vname] = _coerce(_type_name(current), inputs.get("value"), vname)
        self._record(name, ActionResult("Succeeded", inputs=inputs, outputs={"body": {"value": self.ctx.variables[vname]}}))
        return "Succeeded"

    def _do_IncrementVariable(self, name, action):
        inputs = wdl.evaluate_value(action["inputs"], self.ctx)
        self.ctx.variables[inputs["name"]] += inputs.get("value", 1)
        self._record(name, ActionResult("Succeeded", inputs=inputs))
        return "Succeeded"

    def _do_AppendToArrayVariable(self, name, action):
        inputs = wdl.evaluate_value(action["inputs"], self.ctx)
        self.ctx.variables[inputs["name"]].append(inputs["value"])
        self._record(name, ActionResult("Succeeded", inputs=inputs))
        return "Succeeded"

    def _do_Query(self, name, action):  # Filter array
        inputs = action["inputs"]
        source = wdl.evaluate_value(inputs["from"], self.ctx)
        if not isinstance(source, list):
            raise wdl.ExpressionError(f"Filter array 'from' must be an array, got {source!r}")
        kept = []
        for item in source:
            self.ctx.item_stack.append(item)
            try:
                if wdl.evaluate_condition(inputs["where"], self.ctx):
                    kept.append(item)
            finally:
                self.ctx.item_stack.pop()
        self._record(name, ActionResult("Succeeded", inputs={"from": source}, outputs={"body": kept}))
        return "Succeeded"

    def _do_Select(self, name, action):
        inputs = action["inputs"]
        source = wdl.evaluate_value(inputs["from"], self.ctx)
        rows = []
        for item in source:
            self.ctx.item_stack.append(item)
            try:
                rows.append(wdl.evaluate_value(inputs["select"], self.ctx))
            finally:
                self.ctx.item_stack.pop()
        self._record(name, ActionResult("Succeeded", inputs={"from": source}, outputs={"body": rows}))
        return "Succeeded"

    def _do_Table(self, name, action):  # Create HTML table / Create CSV table
        inputs = action["inputs"]
        source = wdl.evaluate_value(inputs["from"], self.ctx)
        if not isinstance(source, list):
            raise wdl.ExpressionError(f"Create table 'from' must be an array, got {source!r}")
        columns = inputs.get("columns")
        rows = []
        for item in source:
            self.ctx.item_stack.append(item)
            try:
                if columns:
                    rows.append([(c["header"], wdl.evaluate_value(c["value"], self.ctx)) for c in columns])
                else:
                    rows.append(list(item.items()))
            finally:
                self.ctx.item_stack.pop()
        headers = [c["header"] for c in columns] if columns else [k for k, _ in (rows[0] if rows else [])]
        if inputs.get("format", "CSV").upper() == "HTML":
            head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
            body = "".join("<tr>" + "".join(f"<td>{html.escape(wdl.to_text(v))}</td>" for _, v in r) + "</tr>" for r in rows)
            out = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        else:
            # Assumption (not on Learn): values with a comma, quote or line break are quoted, RFC 4180 style.
            def cell(text):
                return '"' + text.replace('"', '""') + '"' if any(ch in text for ch in ',"\r\n') else text
            out = "\r\n".join([",".join(cell(h) for h in headers)] +
                                [",".join(cell(wdl.to_text(v)) for _, v in r) for r in rows])
        self._record(name, ActionResult("Succeeded", inputs={"from": source}, outputs={"body": out}))
        return "Succeeded"

    # --- control
    def _do_If(self, name, action):
        branch = wdl.evaluate_condition(action["expression"], self.ctx)
        taken = action.get("actions", {}) if branch else action.get("else", {}).get("actions", {})
        other = action.get("else", {}).get("actions", {}) if branch else action.get("actions", {})
        self._record(name, ActionResult("Running", inputs={"expressionResult": branch}))
        self._skip_all(other)
        status = self._run_scope(taken)
        self._finish(name, status, {"expressionResult": branch})
        return status

    def _do_Switch(self, name, action):
        value = wdl.evaluate_value(action["expression"], self.ctx)
        chosen = None
        for case in action.get("cases", {}).values():
            if wdl._equals(case.get("case"), value) and type(case.get("case")) is type(value):
                chosen = case
                break
        branches = list(action.get("cases", {}).values()) + [action.get("default", {})]
        target = chosen if chosen is not None else action.get("default", {})
        self._record(name, ActionResult("Running", inputs={"expressionResult": value}))
        for b in branches:
            if b is not target:
                self._skip_all(b.get("actions", {}))
        status = self._run_scope(target.get("actions", {}))
        self._finish(name, status, {"expressionResult": value})
        return status

    def _do_Scope(self, name, action):
        self._record(name, ActionResult("Running"))
        status = self._run_scope(action.get("actions", {}))
        self._finish(name, status, None)
        return status

    def _do_Foreach(self, name, action):
        items = wdl.evaluate_value(action["foreach"], self.ctx)
        if not isinstance(items, list):
            raise wdl.ExpressionError(f"Apply to each needs an array, got {items!r}")
        self._record(name, ActionResult("Running", inputs={"count": len(items)}))
        status = "Succeeded"
        for item in items:
            self.ctx.loop_items[name] = item
            self.ctx.item_stack.append(item)
            try:
                if self._run_scope(action.get("actions", {})) == "Failed":
                    status = "Failed"
            finally:
                self.ctx.item_stack.pop()
                self.ctx.loop_items.pop(name, None)
        self._finish(name, status, {"count": len(items)})
        return status

    def _do_Terminate(self, name, action):
        inputs = wdl.evaluate_value(action.get("inputs", {}), self.ctx)
        self._record(name, ActionResult("Succeeded", inputs=inputs))
        raise _Terminate(inputs.get("runStatus", "Succeeded"), inputs.get("runError"))

    def _do_Until(self, name, action):
        limit = action.get("limit") or {}
        max_count = int(limit.get("count", 60))  # Learn: Until iterations default 60, maximum 5,000
        self._record(name, ActionResult("Running"))
        status, n = "Succeeded", 0
        while n < max_count:
            n += 1
            status = self._run_scope(action.get("actions", {}))
            if wdl.evaluate_condition(action["expression"], self.ctx):
                break
        self._finish(name, status, {"iterations": n})
        self.result.actions[name].iterations = n
        return status

    def _do_Http(self, name, action):
        inputs = wdl.evaluate_value(action.get("inputs", {}), self.ctx)
        try:
            out = self.http.call(inputs)
        except HttpCallError as e:
            raise SimulationError(f"{name}: {e}") from None
        status = "Succeeded" if out.status_code < 400 else "Failed"
        outputs = {"statusCode": out.status_code, "headers": out.headers, "body": out.body}
        error = None if status == "Succeeded" else f"{out.status_code}: {json_snippet(out.body)}"
        res = ActionResult(status, inputs=inputs, outputs=outputs, error=error,
                           attempts=[(a.status, a.wait_after) for a in out.attempts])
        self._record(name, res)
        return status

    def _secure(self, name, action, status):
        """Secure inputs/outputs: hidden in the run history (RunResult), still usable by later actions."""
        props = ((action.get("runtimeConfiguration") or {}).get("secureData") or {}).get("properties") or []
        res = self.result.actions.get(name)
        if res is not None and props:
            masked = copy.copy(res)
            if "inputs" in props:
                masked.inputs = SECURED
            if "outputs" in props:
                masked.outputs = SECURED
            self.result.actions[name] = masked
            self.result.history = [(n, masked if r is res else r) for n, r in self.result.history]
        return status

    def _finish(self, name, status, inputs):
        res = self.result.actions[name]
        res.status, res.inputs = status, inputs
        self.ctx.actions[name]["status"] = status

    # --- connectors
    def _do_connector(self, name, action):
        inputs = wdl.evaluate_value(action.get("inputs", {}), self.ctx)
        if name not in self.mocks:
            raise SimulationError(f"No mock for connector action {name!r} "
                                  f"({inputs.get('host', {}).get('operationId', action.get('type'))})")
        mock = self.mocks[name]
        reply = mock(inputs) if callable(mock) else dict(mock)
        status = reply.get("status", "Succeeded")
        if status == "TimedOut":
            timeout = (action.get("limit") or {}).get("timeout")
            if not timeout:
                raise SimulationError(f"{name} can't time out in this test: the action has no limit.timeout")
            iso_duration_seconds(timeout)
        outputs = {"statusCode": reply.get("statusCode", 200 if status == "Succeeded" else 400),
                   "headers": {}, "body": reply.get("body")}
        if status == "TimedOut":
            outputs = None
        self._record(name, ActionResult(status, inputs=inputs, outputs=outputs,
                                        error=reply.get("error") if status != "Succeeded" else None))
        return status


def scope_status(actions: dict, done: dict[str, str]) -> str:
    """Judge each branch by its last action; a Skipped last action inherits its predecessors' outcome."""
    has_successor = {d for a in actions.values() for d in (a.get("runAfter") or {})}
    leaves = [n for n in actions if n not in has_successor]

    def branch_failed(name: str) -> bool:
        status = done[name]
        if status == "Skipped":
            return any(branch_failed(p) for p in (actions[name].get("runAfter") or {}))
        return status in FAILED_STATUSES

    return "Failed" if any(branch_failed(n) for n in leaves) else "Succeeded"


def _type_name(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _coerce(vtype: str, value, name: str):
    vtype = vtype.lower()
    ok = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }[vtype]
    if value is None:
        return None
    if not ok(value):
        raise wdl.ExpressionError(f"variable {name!r} is {vtype} but the value is {value!r}")
    return float(value) if vtype == "float" else value


def json_snippet(body, limit: int = 160) -> str:
    import json
    text = body if isinstance(body, str) else json.dumps(body)
    return text[:limit]


def run_flow(flow: dict, trigger_body=None, mocks=None, now=None, parameters=None, sleep=None) -> RunResult:
    """Convenience wrapper: Simulator(flow, mocks, now, parameters, sleep).run(trigger_body)."""
    return Simulator(flow, mocks=mocks, now=now, parameters=parameters, sleep=sleep).run(trigger_body)
