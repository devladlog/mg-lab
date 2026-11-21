"""Registration as data: the JSON bodies for plug-in assembly, plug-in types, custom API, steps, images and the
risk score column, plus the rules Learn documents for them. Nothing here calls the network.

Shapes follow Microsoft Learn:
- Create a custom API with code (deep insert with CustomAPIRequestParameters / CustomAPIResponseProperties)
- CustomAPI tables (types, which properties can't change after creation)
- SdkMessageProcessingStep / SdkMessageProcessingStepImage / PluginAssembly table references
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Tuple

ODATA = "Microsoft.Dynamics.CRM."
LCID = 1033

# CustomAPIRequestParameter.Type / CustomAPIResponseProperty.Type (Learn: CustomAPI tables)
API_TYPES = {"Boolean": 0, "DateTime": 1, "Decimal": 2, "Entity": 3, "EntityCollection": 4, "EntityReference": 5,
             "Float": 6, "Integer": 7, "Money": 8, "Picklist": 9, "String": 10, "StringArray": 11, "Guid": 12}
NOT_FOR_WORKFLOW = {"Entity", "EntityCollection", "StringArray"}

# "Cannot be changed after it is saved." (Learn: CustomAPI tables)
API_IMMUTABLE = ("uniquename", "bindingtype", "boundentitylogicalname", "isfunction",
                 "allowedcustomprocessingsteptype", "workflowsdkstepenabled")
API_MUTABLE = ("displayname", "description", "isprivate", "executeprivilegename", "name")
PROP_IMMUTABLE = ("uniquename", "type", "logicalentityname")
PARAM_IMMUTABLE = PROP_IMMUTABLE + ("isoptional",)

STAGES = {10: "PreValidation", 20: "PreOperation", 30: "MainOperation", 40: "PostOperation"}
MODES = {0: "Synchronous", 1: "Asynchronous"}
IMAGE_POST = 1                   # SdkMessageProcessingStepImage.ImageType: 0 Pre, 1 Post, 2 Both
ISOLATION_SANDBOX, SOURCE_DATABASE = 2, 0


class ConfigError(ValueError):
    pass


def validate(cfg: Dict[str, Any]) -> List[str]:
    """Learn's rules, checked before anything is sent. Returns the list of problems (empty = fine)."""
    problems: List[str] = []
    api = cfg["custom_api"]
    prefix = cfg["table"].split("_", 1)[0] + "_"
    if not api["uniquename"].startswith(prefix):
        problems.append(f"custom API uniquename must start with the publisher prefix '{prefix}'")
    if api["bindingtype"] == 1 and api.get("boundentitylogicalname") != cfg["table"]:
        problems.append("Entity binding needs boundentitylogicalname = the table")
    if any(p["uniquename"] == "Target" for p in api["request_parameters"]) and api["bindingtype"] == 1:
        problems.append("don't define Target: Entity binding creates it for you")
    for p in api["request_parameters"] + api["response_properties"]:
        if p["type"] not in API_TYPES:
            problems.append(f"{p['uniquename']}: unknown type {p['type']}")
    if api["isfunction"] and not api["response_properties"]:
        problems.append("a function must have at least one response property")
    if api.get("workflowsdkstepenabled"):
        if api["isfunction"]:
            problems.append("Enabled for Workflow can't be a function")
        bad = [p["uniquename"] for p in api["request_parameters"] + api["response_properties"]
               if p["type"] in NOT_FOR_WORKFLOW]
        if bad:
            problems.append(f"Enabled for Workflow can't use Entity, EntityCollection or StringArray: {', '.join(bad)}")
    called_from_plugins = any(s["plugintype"] != api["plugintype"] for s in cfg["steps"])
    if api["isprivate"] and called_from_plugins:
        problems.append("isprivate: private messages can't be used in plug-ins, and RiskScoreRefreshPlugin calls it")
    if api["isfunction"] and api.get("used_from_power_automate"):
        problems.append("the Dataverse connector only performs actions: a function can't be called from a flow")
    for s in cfg["steps"]:
        label = f"step {s['message']}"
        if s["mode"] == 1 and s["stage"] != 40:
            problems.append(f"{label}: asynchronous steps can only be registered for PostOperation (40)")
        if s.get("filteringattributes") and s["message"] != "Update":
            problems.append(f"{label}: filtering attributes only apply to Update")
        if s["message"] == "Update" and not s.get("filteringattributes"):
            problems.append(f"{label}: set filtering attributes, or every update of any column runs the plug-in")
        if s.get("post_image") and s["stage"] != 40:
            problems.append(f"{label}: post-images only exist in PostOperation")
        if cfg["column"]["schema"].lower() in [a.lower() for a in s.get("filteringattributes", [])]:
            problems.append(f"{label}: the plug-in writes {cfg['column']['schema'].lower()}; filtering on it loops")
    return problems


def assembly_body(name: str, dll: bytes) -> Dict[str, Any]:
    """PluginAssembly: content is the base64 DLL; most other properties are read from the DLL by reflection."""
    return {"name": name, "content": base64.b64encode(dll).decode("ascii"),
            "isolationmode": ISOLATION_SANDBOX, "sourcetype": SOURCE_DATABASE}


def plugintype_body(assembly_id: str, typename: str, friendlyname: str) -> Dict[str, Any]:
    return {"typename": typename, "name": typename, "friendlyname": friendlyname,
            "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})"}


def _prop(api_name: str, p: Dict[str, Any], *, request: bool) -> Dict[str, Any]:
    body = {"uniquename": p["uniquename"], "name": f"{api_name}.{p['uniquename']}",
            "displayname": p.get("displayname", p["uniquename"]), "description": p.get("description", ""),
            "type": API_TYPES[p["type"]], "logicalentityname": p.get("logicalentityname")}
    if request:
        body["isoptional"] = bool(p.get("isoptional", False))
    return body


def custom_api_body(cfg: Dict[str, Any], plugintype_id: str) -> Dict[str, Any]:
    """One POST /customapis creates the API with its parameters and properties (deep insert, Learn sample)."""
    api = cfg["custom_api"]
    name = api["uniquename"]
    return {
        "uniquename": name, "name": name, "displayname": api["displayname"], "description": api["description"],
        "bindingtype": api["bindingtype"], "boundentitylogicalname": api.get("boundentitylogicalname"),
        "isfunction": api["isfunction"], "isprivate": api["isprivate"],
        "allowedcustomprocessingsteptype": api["allowedcustomprocessingsteptype"],
        "workflowsdkstepenabled": api.get("workflowsdkstepenabled", False),
        "executeprivilegename": api.get("executeprivilegename"),
        "CustomAPIRequestParameters": [_prop(name, p, request=True) for p in api["request_parameters"]],
        "CustomAPIResponseProperties": [_prop(name, p, request=False) for p in api["response_properties"]],
        "PluginTypeId@odata.bind": f"/plugintypes({plugintype_id})",
    }


def diff_custom_api(existing: Dict[str, Any], desired: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str],
                                                                               List[Dict[str, Any]], List[str]]:
    """Compare a deployed API (GET with $expand) with the desired body.

    Returns (mutable changes to PATCH, immutable conflicts, response properties to add, response properties only on
    the server). An immutable conflict can't be fixed by PATCH: delete the API and create it again.
    """
    patch = {k: desired[k] for k in API_MUTABLE if existing.get(k) != desired.get(k)}
    conflicts = [f"{k}: {existing.get(k)!r} -> {desired.get(k)!r}" for k in API_IMMUTABLE
                 if existing.get(k) != desired.get(k)]
    have = {p["uniquename"]: p for p in existing.get("CustomAPIResponseProperties", [])}
    add = []
    for p in desired["CustomAPIResponseProperties"]:
        old = have.get(p["uniquename"])
        if old is None:
            add.append(p)
            continue
        conflicts += [f"{p['uniquename']}.{k}: {old.get(k)!r} -> {p.get(k)!r}" for k in PROP_IMMUTABLE
                      if old.get(k) != p.get(k)]
    want = {p["uniquename"] for p in desired["CustomAPIResponseProperties"]}
    extra = sorted(set(have) - want)
    have_req = {p["uniquename"]: p for p in existing.get("CustomAPIRequestParameters", [])}
    for p in desired["CustomAPIRequestParameters"]:
        old = have_req.get(p["uniquename"])
        if old is None:
            conflicts.append(f"request parameter {p['uniquename']} is new: add it by hand or recreate the API")
        else:
            conflicts += [f"{p['uniquename']}.{k}: {old.get(k)!r} -> {p.get(k)!r}" for k in PARAM_IMMUTABLE
                          if old.get(k) != p.get(k)]
    return patch, conflicts, add, extra


def step_name(step: Dict[str, Any], table: str) -> str:
    return f"{step['plugintype']}: {step['message']} of {table}"


def step_body(step: Dict[str, Any], table: str, plugintype_id: str, message_id: str, filter_id: str) -> Dict[str, Any]:
    body = {
        "name": step_name(step, table),
        "mode": step["mode"], "stage": step["stage"], "rank": step.get("rank", 1), "supporteddeployment": 0,
        "asyncautodelete": bool(step.get("asyncautodelete", False)) if step["mode"] == 1 else False,
        "filteringattributes": ",".join(step.get("filteringattributes", [])) or None,
        "eventhandler_plugintype@odata.bind": f"/plugintypes({plugintype_id})",
        "sdkmessageid@odata.bind": f"/sdkmessages({message_id})",
        "sdkmessagefilterid@odata.bind": f"/sdkmessagefilters({filter_id})",
    }
    return body


STEP_COMPARE = ("mode", "stage", "rank", "asyncautodelete", "filteringattributes")


def step_changes(existing: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
    def norm(k, v):
        if k == "filteringattributes":
            return ",".join(sorted(a for a in (v or "").split(",") if a))
        return v
    return {k: desired[k] for k in STEP_COMPARE if norm(k, existing.get(k)) != norm(k, desired.get(k))}


def post_image_body(step_id: str, attributes: List[str]) -> Dict[str, Any]:
    # Learn (Register a plug-in > Define entity images): the message property is Target for Create and Update.
    return {"name": "PostImage", "entityalias": "PostImage", "imagetype": IMAGE_POST,
            "messagepropertyname": "Target", "attributes": ",".join(attributes),
            "sdkmessageprocessingstepid@odata.bind": f"/sdkmessageprocessingsteps({step_id})"}


def label(text: str) -> Dict[str, Any]:
    return {"@odata.type": ODATA + "Label",
            "LocalizedLabels": [{"@odata.type": ODATA + "LocalizedLabel", "Label": text, "LanguageCode": LCID}]}


def integer_column(col: Dict[str, Any]) -> Dict[str, Any]:
    """IntegerAttributeMetadata for POST EntityDefinitions(LogicalName='...')/Attributes."""
    return {
        "@odata.type": ODATA + "IntegerAttributeMetadata",
        "AttributeType": "Integer",
        "AttributeTypeName": {"Value": "IntegerType"},
        "SchemaName": col["schema"],
        "DisplayName": label(col["display"]),
        "Description": label(col["description"]),
        "RequiredLevel": {"Value": "None", "CanBeChanged": True,
                          "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings"},
        "Format": "None",
        "MinValue": col["min"],
        "MaxValue": col["max"],
    }
