"""Review a cloud flow that Copilot generated, from its definition JSON.

The input is the flow file of a solution (Workflows/<name>-<guid>.json after `pac solution unpack`: an object with
properties.definition and properties.connectionReferences) or a bare definition (triggers + actions).
Nothing here runs the flow. Rules and where they come from:

  FR001  literal e-mail recipient           Learn's own Copilot examples put addresses in the prompt, and the flow keeps them
  FR002  no failure path                    Learn (Copilot tips): error handling = a Scope with a run-after Failed/TimedOut branch
  FR003  message sent inside a loop         one message per item (a design question, not a bug)
  FR005  Recurrence without a time zone     Learn (Recurrence trigger): without a time zone, DST changes can move the run
  FR008  legacy (non Open API) connection   Learn (Copilot in cloud flows FAQ): the designer with Copilot cannot edit such flows
  FR009  connection instead of reference    Learn (same FAQ): solution flows must use connection references
  FR010  expression problems                see expressions.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from .expressions import check_expression
from .findings import Finding

EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
RECIPIENT_KEYS = {"to", "cc", "bcc", "recipient", "recipients"}
# Operations that tell a person something. Office 365 Outlook "Send an email (V2)" and the Teams post actions.
MESSAGE_OPS = {"SendEmailV2", "SendEmail", "PostMessageToConversation", "PostCardToConversation", "PostMessage"}
# Operations that only read. Everything else on a connector is treated as having a side effect.
READ_PREFIXES = ("Get", "List", "Search", "Find", "Lookup")


def load_flow(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def definition_of(flow: dict) -> dict:
    if "properties" in flow and "definition" in flow["properties"]:
        return flow["properties"]["definition"]
    if "triggers" in flow or "actions" in flow:
        return flow
    raise ValueError("Not a flow: expected properties.definition or a definition with triggers and actions")


def walk_actions(actions: dict, path: str = "", in_loop: bool = False) -> Iterator[tuple[str, dict, bool]]:
    """(path, action, inside a Foreach/Until) for every action, nested ones included."""
    for name, action in (actions or {}).items():
        here = f"{path}/{name}" if path else name
        yield here, action, in_loop
        kind = action.get("type")
        loop = in_loop or kind in ("Foreach", "Until")
        yield from walk_actions(action.get("actions", {}), here, loop)
        yield from walk_actions(action.get("else", {}).get("actions", {}), here, loop)
        for case in action.get("cases", {}).values():
            yield from walk_actions(case.get("actions", {}), here, loop)
        yield from walk_actions(action.get("default", {}).get("actions", {}), here, loop)


def operation_of(action: dict) -> str:
    return (action.get("inputs") or {}).get("host", {}).get("operationId", "") if isinstance(action.get("inputs"), dict) else ""


def _is_dynamic(value: str) -> bool:
    return value.startswith("@") or "@{" in value


def review_flow(flow: dict) -> list[Finding]:
    d = definition_of(flow)
    findings: list[Finding] = []
    actions = list(walk_actions(d.get("actions", {})))

    # FR001 literal recipients
    for path, action, _ in actions:
        params = (action.get("inputs") or {}).get("parameters", {}) if isinstance(action.get("inputs"), dict) else {}
        for key, value in params.items():
            leaf = key.split("/")[-1].lower()
            if leaf in RECIPIENT_KEYS and isinstance(value, str) and not _is_dynamic(value):
                for address in re.split(r"[;,]", value):
                    if EMAIL.match(address.strip()):
                        findings.append(Finding("FR001", "warning", path,
                            f"'{key}' is the literal address {address.strip()}. Use dynamic content, a parameter or an environment variable."))

    # FR002 no failure path while the flow changes something or tells someone
    side_effects = [p for p, a, _ in actions if a.get("type") in ("OpenApiConnection", "ApiConnection")
                    and operation_of(a) and not operation_of(a).startswith(READ_PREFIXES)]
    has_failure_path = any(
        status in ("Failed", "TimedOut")
        for _, a, _ in actions for statuses in (a.get("runAfter") or {}).values() for status in statuses
    )
    if side_effects and not has_failure_path:
        findings.append(Finding("FR002", "warning", "flow",
            f"{len(side_effects)} action(s) with side effects and no action that runs after a failure. "
            "Wrap the work in a Scope and add a second Scope that runs after Failed or TimedOut (Learn: Copilot can add it if you ask)."))

    # FR003 messages inside loops
    for path, action, in_loop in actions:
        if in_loop and operation_of(action) in MESSAGE_OPS:
            findings.append(Finding("FR003", "info", path,
                "Sends a message inside a loop: one per item. Check how many items the query can return, or send one summary."))

    # FR005 recurrence without time zone
    for name, trigger in (d.get("triggers") or {}).items():
        if trigger.get("type") == "Recurrence":
            rec = trigger.get("recurrence", {})
            if not rec.get("timeZone"):
                findings.append(Finding("FR005", "warning", name,
                    "Recurrence has no time zone. Learn: select one, otherwise daylight saving changes can move the run time."))

    # FR010 expressions
    for where, text in _expressions(d):
        for f in check_expression(text, where):
            findings.append(Finding("FR010", f.severity, where, f"{f.code}: {f.message}"))

    findings.extend(designer_blockers(flow))
    return findings


def designer_blockers(flow: dict) -> list[Finding]:
    """What the Copilot FAQ says stops the designer with Copilot from editing a flow (only what can be seen in the JSON)."""
    out: list[Finding] = []
    d = definition_of(flow)
    for path, action, _ in walk_actions(d.get("actions", {})):
        if action.get("type") == "ApiConnection":
            out.append(Finding("FR008", "warning", path,
                "Legacy connection format (ApiConnection, not OpenApiConnection): the designer with Copilot cannot edit this flow."))
    for name, trigger in (d.get("triggers") or {}).items():
        if trigger.get("type") == "ApiConnection":
            out.append(Finding("FR008", "warning", name,
                "Legacy connection format (ApiConnection, not OpenApiConnection): the designer with Copilot cannot edit this flow."))
    refs = flow.get("properties", {}).get("connectionReferences", {}) if "properties" in flow else {}
    for key, ref in refs.items():
        if not (ref.get("connection") or {}).get("connectionReferenceLogicalName"):
            out.append(Finding("FR009", "warning", f"connectionReferences/{key}",
                "No connection reference logical name: a solution flow that uses connections instead of connection references "
                "is not supported by the designer with Copilot."))
    return out


def _expressions(node, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string value that is an expression: starts with @ (not @@) or has @{ ... } inside."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("$schema",):
                continue
            yield from _expressions(v, f"{path}/{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _expressions(v, f"{path}[{i}]")
    elif isinstance(node, str):
        if node.startswith("@") and not node.startswith("@@"):
            yield path, node
        else:
            for m in re.finditer(r"@\{(.*?)\}", node):
                yield path, "@{" + m.group(1) + "}"
