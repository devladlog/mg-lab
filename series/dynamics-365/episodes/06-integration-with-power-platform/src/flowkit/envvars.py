"""Environment variables: definitions go in the solution, values don't.

Learn (Environment variables overview, FAQ "Should I include the value in my solution?"): No. Include the definition;
provide the value for the target environment during deployment (deployment settings file). So `ensure` creates the
definition with MSCRM.SolutionUniqueName and the value WITHOUT it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .webapi import WebApi, odata_string

# EnvironmentVariableDefinition.Type (Learn table reference)
TYPES = {"String": 100000000, "Number": 100000001, "Boolean": 100000002, "JSON": 100000003,
         "Data Source": 100000004, "Secret": 100000005}


def definition_body(ev: Dict[str, Any]) -> Dict[str, Any]:
    body = {"schemaname": ev["schemaname"], "displayname": ev["displayname"], "type": TYPES[ev["type"]],
            "description": ev.get("description", "")}
    if ev.get("default") is not None:
        body["defaultvalue"] = str(ev["default"])
    return body


def value_body(definition_id: str, schemaname: str, value: str) -> Dict[str, Any]:
    return {"schemaname": schemaname, "value": value,
            "EnvironmentVariableDefinitionId@odata.bind": f"/environmentvariabledefinitions({definition_id})"}


def ensure(api: WebApi, cfg: Dict[str, Any], values: Dict[str, str], out=print) -> Dict[str, str]:
    """Create missing definitions (in the solution) and create or update the values given (outside it)."""
    unknown = set(values) - {ev["schemaname"] for ev in cfg["environment_variables"]}
    if unknown:
        raise ValueError(f"not in flow.json: {', '.join(sorted(unknown))}")
    ids: Dict[str, str] = {}
    for ev in cfg["environment_variables"]:
        name = ev["schemaname"]
        rows = api.get(f"environmentvariabledefinitions?$select=environmentvariabledefinitionid,type"
                       f"&$filter=schemaname eq {odata_string(name)}")["value"]
        if rows:
            ids[name] = rows[0]["environmentvariabledefinitionid"]
            if rows[0].get("type") != TYPES[ev["type"]]:
                out(f"! {name}: type on the server is {rows[0].get('type')}, flow.json says {ev['type']} (left alone)")
        else:
            ids[name] = api.create("environmentvariabledefinitions", definition_body(ev), in_solution=True)
            out(f"+ definition {name} ({ev['type']}) in {cfg['solution']}")
        if name in values:
            current = api.get(f"environmentvariablevalues?$select=environmentvariablevalueid,value"
                              f"&$filter=schemaname eq {odata_string(name)}")["value"]
            if not current:
                api.create("environmentvariablevalues", value_body(ids[name], name, values[name]), in_solution=False)
                out(f"+ value {name} (not in the solution)")
            elif current[0].get("value") != values[name]:
                api.update(f"environmentvariablevalues({current[0]['environmentvariablevalueid']})",
                           {"value": values[name]}, in_solution=False)
                out(f"~ value {name}: changed. Flows keep the old value until saved or turned off and on: flowkit restart")
            else:
                out(f"= value {name} unchanged")
    return ids


def current_values(api: WebApi, cfg: Dict[str, Any]) -> Dict[str, Optional[str]]:
    found: Dict[str, Optional[str]] = {}
    for ev in cfg["environment_variables"]:
        rows = api.get(f"environmentvariablevalues?$select=value&$filter=schemaname eq {odata_string(ev['schemaname'])}")["value"]
        found[ev["schemaname"]] = rows[0]["value"] if rows else None
    return found


def parse_assignments(items: List[str]) -> Dict[str, str]:
    values = {}
    for item in items or []:
        name, sep, val = item.partition("=")
        if not sep or not name:
            raise ValueError(f"expected NAME=VALUE, got {item!r}")
        values[name.strip()] = val
    return values
