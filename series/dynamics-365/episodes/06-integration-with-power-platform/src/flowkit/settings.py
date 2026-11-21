"""Deployment settings file (Learn: Pre-populate connection references and environment variables for automated
deployments). Same shape as `pac solution create-settings` produces:

{"EnvironmentVariables": [{"SchemaName", "Value"}], "ConnectionReferences": [{"LogicalName", "ConnectionId", "ConnectorId"}]}

`build` makes the skeleton from the flow and flow.json; `check` refuses a file that would make an import stop and ask.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .definition import Flow

CONNECTOR_PREFIX = "/providers/Microsoft.PowerApps/apis/"


def build(flow: Flow, cfg: Dict[str, Any], values: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, Any]:
    values = values or {}
    env = [{"SchemaName": ev["schemaname"], "Value": values.get(ev["schemaname"]) or ""}
           for ev in cfg["environment_variables"]]
    refs = []
    for key, ref in sorted(flow.connection_references.items()):
        logical = (ref.get("connection") or {}).get("connectionReferenceLogicalName")
        if logical:
            api = (ref.get("api") or {}).get("name", key)
            refs.append({"LogicalName": logical, "ConnectionId": "", "ConnectorId": CONNECTOR_PREFIX + api})
    return {"EnvironmentVariables": env, "ConnectionReferences": refs}


def check(settings: Dict[str, Any], flow: Optional[Flow] = None, cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    problems = []
    for ev in settings.get("EnvironmentVariables", []):
        if not ev.get("SchemaName"):
            problems.append("an environment variable without SchemaName")
        elif ev.get("Value") in (None, ""):
            problems.append(f"{ev['SchemaName']}: empty Value (the import will leave it unset or ask for it)")
    for cr in settings.get("ConnectionReferences", []):
        if not cr.get("ConnectionId"):
            problems.append(f"{cr.get('LogicalName')}: empty ConnectionId (create the connection in the target first)")
        if not str(cr.get("ConnectorId", "")).startswith(CONNECTOR_PREFIX):
            problems.append(f"{cr.get('LogicalName')}: ConnectorId should start with {CONNECTOR_PREFIX}")
    if flow is not None:
        have = {cr.get("LogicalName") for cr in settings.get("ConnectionReferences", [])}
        for key, ref in flow.connection_references.items():
            logical = (ref.get("connection") or {}).get("connectionReferenceLogicalName")
            if logical and logical not in have:
                problems.append(f"{logical}: used by the flow but missing from the settings file")
    if cfg is not None:
        have_env = {ev.get("SchemaName") for ev in settings.get("EnvironmentVariables", [])}
        for ev in cfg["environment_variables"]:
            if ev["schemaname"] not in have_env:
                problems.append(f"{ev['schemaname']}: missing from the settings file")
    return problems
