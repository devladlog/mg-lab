"""Read a cloud flow's `clientdata` (Learn: "a string-encoded JSON of the flow definition and its
connectionReferences") and lint it for the mistakes that bite Dataverse flows.

The definition is the Logic Apps workflow definition language: triggers, actions (nested in If/Scope/Switch/Foreach),
parameters. Connector calls are `OpenApiConnection` (actions) or `OpenApiConnectionWebhook` (the Dataverse row
trigger) with `inputs.host.operationId` and `inputs.parameters`.

Parameter keys of the Dataverse trigger are matched by their last segment (`filteringattributes`, `filterexpression`,
`entityname`) because exports prefix them (for example `subscriptionRequest/filteringattributes`); the connector
reference documents the bare keys.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

ROW_TRIGGER = "SubscribeWebhookTrigger"            # When a row is added, modified or deleted
UPDATE_OPS = {"UpdateOnlyRecord", "UpdateRecord"}  # Update a row / Upsert a row
BOUND_ACTION = "PerformBoundAction"
TEAMS_POST = "PostMessageToConversation"
BUILT_IN_PARAMETERS = {"$connections", "$authentication"}
PARAM_REF = re.compile(r"parameters\('([^']+)'\)")


@dataclass(frozen=True)
class Finding:
    level: str      # error | warning | info
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():<7} {self.code}  {self.message}"


def load_clientdata(raw: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if "properties" not in data or "definition" not in data["properties"]:
        raise ValueError("not a cloud flow clientdata: expected properties.definition")
    return data


def last_segment(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def walk_actions(actions: Dict[str, Any], path: str = "") -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Every action, including those inside If (actions/else), Switch (cases/default), Scope and Foreach."""
    for name, action in (actions or {}).items():
        full = f"{path}{name}"
        yield full, action
        yield from walk_actions(action.get("actions", {}), full + "/")
        yield from walk_actions(action.get("else", {}).get("actions", {}), full + "/else/")
        for case, body in action.get("cases", {}).items():
            yield from walk_actions(body.get("actions", {}), f"{full}/{case}/")
        yield from walk_actions(action.get("default", {}).get("actions", {}), full + "/default/")


def operation(step: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """(api name, operationId, parameters) for a connector step; (None, None, {}) otherwise."""
    inputs = step.get("inputs") or {}
    host = inputs.get("host") or {}
    api_id = host.get("apiId") or ""
    return (api_id.rsplit("/", 1)[-1] or None), host.get("operationId"), inputs.get("parameters") or {}


class Flow:
    def __init__(self, clientdata: Dict[str, Any]):
        self.data = clientdata
        self.properties = clientdata["properties"]
        self.definition = self.properties["definition"]

    @property
    def connection_references(self) -> Dict[str, Any]:
        return self.properties.get("connectionReferences", {})

    @property
    def parameters(self) -> Dict[str, Any]:
        return self.definition.get("parameters", {})

    def triggers(self) -> Iterator[Tuple[str, Dict[str, Any]]]:
        yield from (self.definition.get("triggers") or {}).items()

    def actions(self) -> Iterator[Tuple[str, Dict[str, Any]]]:
        yield from walk_actions(self.definition.get("actions") or {})

    def row_trigger(self) -> Optional[Tuple[str, Dict[str, str]]]:
        """(name, parameters by last key segment) of the Dataverse row trigger, if the flow has one."""
        for name, t in self.triggers():
            _, op, params = operation(t)
            if op == ROW_TRIGGER:
                return name, {last_segment(k): v for k, v in params.items()}
        return None

    def parameter_refs(self) -> List[str]:
        """Names used as parameters('...') anywhere in triggers and actions."""
        text = json.dumps({"t": self.definition.get("triggers"), "a": self.definition.get("actions")})
        return sorted(set(PARAM_REF.findall(text)))

    def summary(self) -> List[str]:
        lines = []
        rt = self.row_trigger()
        if rt:
            name, p = rt
            lines.append(f"trigger  {name}: table {p.get('entityname')}, select columns "
                         f"{p.get('filteringattributes') or '(none)'}, filter rows {p.get('filterexpression') or '(none)'}")
        else:
            lines += [f"trigger  {n} ({t.get('type')})" for n, t in self.triggers()]
        for name, a in self.actions():
            api, op, _ = operation(a)
            lines.append(f"action   {name}: {op or a.get('type')}" + (f" [{api}]" if api else ""))
        for key, ref in self.connection_references.items():
            logical = (ref.get("connection") or {}).get("connectionReferenceLogicalName", "(no connection reference)")
            lines.append(f"connref  {key} -> {logical}")
        return lines


def columns(csv: Optional[str]) -> List[str]:
    return [c.strip().lower() for c in (csv or "").split(",") if c.strip()]


def env_var_schema(param_name: str, param: Dict[str, Any]) -> Optional[str]:
    """Schema name of an environment variable parameter: metadata.schemaName, or the '(schema)' suffix of its name."""
    meta = (param or {}).get("metadata") or {}
    if meta.get("schemaName"):
        return meta["schemaName"]
    m = re.search(r"\(([A-Za-z0-9_]+)\)\s*$", param_name)
    return m.group(1) if m else None


def lint(flow: Flow, cfg: Dict[str, Any]) -> List[Finding]:
    out: List[Finding] = []
    table, entity_set = cfg["table"], cfg["entity_set"]
    rt = flow.row_trigger()
    watched: List[str] = []
    if rt is None:
        out.append(Finding("info", "F001", "no Dataverse row trigger: trigger checks skipped"))
    else:
        name, p = rt
        watched = columns(p.get("filteringattributes"))
        if p.get("entityname", "").lower() not in (table, entity_set):
            out.append(Finding("warning", "F002", f"trigger table is {p.get('entityname')}, expected {table}"))
        if not watched:
            out.append(Finding("warning", "F010", "no Select columns: every update of any column runs the flow"))
        lookups = sorted(set(watched) & {c.lower() for c in cfg.get("lookup_columns", [])})
        if lookups:
            out.append(Finding("error", "F011", f"lookup columns in Select columns never trigger the flow: {', '.join(lookups)}"))
        if f"{table}id" in watched:
            out.append(Finding("warning", "F012", f"{table}id is in every update: Select columns would match all updates"))
        expr = p.get("filterexpression") or ""
        m = re.search(rf"\b{re.escape(cfg['watched_column'])}\s+ge\s+(\d+)", expr)
        if cfg.get("watched_column") in watched and m and int(m.group(1)) != cfg["high_from"]:
            out.append(Finding("warning", "F030", f"filter rows uses {cfg['watched_column']} ge {m.group(1)} but the "
                               f"plug-in calls a score High from {cfg['high_from']}"))

    for aname, a in flow.actions():
        api, op, params = operation(a)
        if op in UPDATE_OPS:
            target = str(params.get("entityName", "")).lower()
            written = {last_segment(k).lower() for k in params if k.startswith("item/")}
            loop = sorted(written & set(watched))
            if target in (entity_set, table) and loop:
                out.append(Finding("error", "F020", f"{aname} updates {', '.join(loop)} on {target}, which the trigger "
                                   "watches: the flow triggers itself"))
        if op == BOUND_ACTION:
            action = str(params.get("actionName", ""))
            if not action.endswith(cfg["custom_api"]):
                out.append(Finding("warning", "F070", f"{aname} calls {action}, not the episode 5 custom API {cfg['custom_api']}"))
            if str(params.get("entityName", "")).lower() not in (entity_set, table):
                out.append(Finding("warning", "F071", f"{aname} binds to {params.get('entityName')}, expected {entity_set}"))
        if op == TEAMS_POST or api == "shared_teams":
            for k, v in params.items():
                if last_segment(k) in ("groupId", "channelId") and isinstance(v, str) and v and not v.startswith("@"):
                    out.append(Finding("warning", "F060", f"{aname}: {last_segment(k)} is a literal; use an environment "
                                       "variable so test and production post to their own channel"))

    for key, ref in flow.connection_references.items():
        if not (ref.get("connection") or {}).get("connectionReferenceLogicalName"):
            out.append(Finding("error", "F040", f"connection {key} is not a connection reference: the solution "
                               "won't carry it to another environment"))
        api = (ref.get("api") or {}).get("name", key)
        if api not in cfg.get("connectors", {}):
            out.append(Finding("info", "F041", f"connector {api} isn't in flow.json connectors"))

    declared = set(flow.parameters) | BUILT_IN_PARAMETERS
    for ref in flow.parameter_refs():
        if ref not in declared:
            out.append(Finding("error", "F050", f"parameters('{ref}') is used but not declared in the definition"))
    used_env = {env_var_schema(n, p) for n, p in flow.parameters.items()}
    for ev in cfg.get("environment_variables", []):
        if ev["schemaname"] not in used_env:
            out.append(Finding("info", "F051", f"environment variable {ev['schemaname']} isn't used by this flow"))
    return out


def has_errors(findings: List[Finding]) -> bool:
    return any(f.level == "error" for f in findings)
