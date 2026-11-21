"""Deploy episode 3's customizations into an unmanaged solution. Safe to run again: every step checks first.

  1. column    Business Justification (memo) on mgl_projectrequest
  2. script    web resource mgl_/projectrequest/form.js, created or updated only when the bytes changed
  3. form      library + OnLoad handler registered in the main form's FormXml; warns about missing fields
  4. view      "Open requests over 50,000" public view (fetchxml + layoutxml with the real ObjectTypeCode)
  5. publish   PublishXml for the table and the updated web resource
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import components, formxml
from .webapi import DataverseError, WebApi, odata_string

Out = Callable[[str], None]


@dataclass
class DeployReport:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def ensure_column(api: WebApi, cfg: Dict[str, Any], rep: DeployReport, out: Out) -> None:
    table, col = cfg["table"], cfg["column"]["logical_name"]
    path = f"EntityDefinitions(LogicalName='{table}')/Attributes(LogicalName='{col}')?$select=LogicalName"
    if api.exists(path):
        rep.unchanged.append(f"column {col}")
        out(f"  = column {col} exists")
        return
    api.request("POST", f"EntityDefinitions(LogicalName='{table}')/Attributes",
                json=components.justification_column(cfg), in_solution=True)
    rep.created.append(f"column {col}")
    out(f"  + column {cfg['column']['schema_name']} (Memo, {cfg['column']['max_length']} chars)")


def ensure_webresource(api: WebApi, cfg: Dict[str, Any], script: bytes, rep: DeployReport, out: Out) -> Optional[str]:
    """Returns the id of the web resource when it was UPDATED (needs publishing), else None."""
    body = components.webresource(cfg, script)
    name = body["name"]
    found = api.get(f"webresourceset?$select=webresourceid,content&$filter=name eq {odata_string(name)}")["value"]
    if not found:
        wr_id = api.create("webresourceset", body)
        rep.created.append(f"web resource {name}")
        out(f"  + web resource {name} ({len(script):,} bytes)")
        return None          # Learn: new web resources don't need publishing; updated ones do
    wr_id = found[0]["webresourceid"]
    current = base64.b64decode(found[0].get("content") or "")
    if current == script:
        rep.unchanged.append(f"web resource {name}")
        out(f"  = web resource {name} unchanged")
        return None
    api.update(f"webresourceset({wr_id})", {"content": body["content"], "displayname": body["displayname"]})
    rep.updated.append(f"web resource {name}")
    out(f"  ~ web resource {name} updated ({len(script):,} bytes)")
    return wr_id


def find_main_form(api: WebApi, table: str, name: str) -> Dict[str, Any]:
    # type 2 = Main form. Same filter shape as Learn's troubleshooting script: objecttypecode eq '<logical name>'.
    forms = api.get(f"systemforms?$select=formid,name,formxml"
                    f"&$filter=objecttypecode eq {odata_string(table)} and type eq 2")["value"]
    for f in forms:
        if f["name"] == name:
            return f
    names = ", ".join(sorted(f["name"] for f in forms)) or "none"
    raise DataverseError(404, "FormNotFound", f"main form {name!r} not found on {table} (main forms: {names})")


def ensure_form(api: WebApi, cfg: Dict[str, Any], rep: DeployReport, out: Out) -> None:
    form = find_main_form(api, cfg["table"], cfg["form"]["name"])
    res = formxml.register_onload(form["formxml"], cfg["webresource"]["name"], cfg["form"]["onload"])
    if res.changed:
        api.update(f"systemforms({form['formid']})", {"formxml": res.xml})
        rep.updated.append(f"form {form['name']}")
        for a in res.actions:
            out(f"  ~ form {form['name']}: {a}")
    else:
        rep.unchanged.append(f"form {form['name']}")
        out(f"  = form {form['name']}: handler already registered")
    for f in formxml.missing_fields(res.xml, cfg["form"]["required_fields"]):
        msg = f"form {form['name']} has no control for {f}: add it in the form designer"
        rep.warnings.append(msg)
        out(f"  ! {msg}")


def object_type_code(api: WebApi, table: str) -> int:
    return int(api.get(f"EntityDefinitions(LogicalName='{table}')?$select=ObjectTypeCode")["ObjectTypeCode"])


def ensure_view(api: WebApi, cfg: Dict[str, Any], rep: DeployReport, out: Out) -> None:
    body = components.savedquery(cfg, object_type_code(api, cfg["table"]))
    found = api.get("savedqueries?$select=savedqueryid,fetchxml,layoutxml"
                    f"&$filter=returnedtypecode eq {odata_string(cfg['table'])} and querytype eq 0"
                    f" and name eq {odata_string(body['name'])}")["value"]
    if not found:
        api.create("savedqueries", body)
        rep.created.append(f"view {body['name']}")
        out(f"  + view '{body['name']}'")
        return
    current = found[0]
    if current.get("fetchxml") == body["fetchxml"] and current.get("layoutxml") == body["layoutxml"]:
        rep.unchanged.append(f"view {body['name']}")
        out(f"  = view '{body['name']}' unchanged")
        return
    api.update(f"savedqueries({current['savedqueryid']})",
               {"fetchxml": body["fetchxml"], "layoutxml": body["layoutxml"], "description": body["description"]})
    rep.updated.append(f"view {body['name']}")
    out(f"  ~ view '{body['name']}' updated")


def deploy(api: WebApi, cfg: Dict[str, Any], script: bytes, out: Out = print) -> DeployReport:
    rep = DeployReport()
    out(f"solution {api.solution}  table {cfg['table']}")
    ensure_column(api, cfg, rep, out)
    updated_wr = ensure_webresource(api, cfg, script, rep, out)
    ensure_form(api, cfg, rep, out)
    ensure_view(api, cfg, rep, out)
    if rep.created or rep.updated:
        api.action("PublishXml", {"ParameterXml": components.publish_xml(cfg["table"],
                                                                         [updated_wr] if updated_wr else [])})
        out("  published")
    else:
        out("  nothing to publish")
    out(f"{len(rep.created)} created, {len(rep.updated)} updated, {len(rep.unchanged)} unchanged, "
        f"{len(rep.warnings)} warning(s)")
    return rep


def remove(api: WebApi, cfg: Dict[str, Any], out: Out = print) -> None:
    """Tear-down of what deploy added, in dependency order. The column is kept unless asked (it holds data)."""
    form = find_main_form(api, cfg["table"], cfg["form"]["name"])
    res = formxml.unregister(form["formxml"], cfg["webresource"]["name"])
    if res.changed:
        api.update(f"systemforms({form['formid']})", {"formxml": res.xml})
        out(f"  - form {form['name']}: " + "; ".join(res.actions))
    views = api.get("savedqueries?$select=savedqueryid"
                    f"&$filter=returnedtypecode eq {odata_string(cfg['table'])} and querytype eq 0"
                    f" and name eq {odata_string(cfg['view']['name'])}")["value"]
    for v in views:
        api.delete(f"savedqueries({v['savedqueryid']})")
        out(f"  - view '{cfg['view']['name']}'")
    api.action("PublishXml", {"ParameterXml": components.publish_xml(cfg["table"])})
    # The web resource can only go once no published form depends on it, so it's deleted after publishing.
    wrs = api.get("webresourceset?$select=webresourceid"
                  f"&$filter=name eq {odata_string(cfg['webresource']['name'])}")["value"]
    for w in wrs:
        api.delete(f"webresourceset({w['webresourceid']})")
        out(f"  - web resource {cfg['webresource']['name']}")


def probe_rule(api: WebApi, cfg: Dict[str, Any], budget: int, out: Out = print) -> bool:
    """Does the server enforce the justification rule? Try to CREATE a throwaway request through the API with a
    budget over the threshold and no justification. Returns True if the server refused it.

    Learn: a business rule with scope Entity runs on model-driven forms AND on the server, but only the
    set/clear value, default value and validate + show error message actions run there; requirement levels,
    visibility and locking are form-only. So only a "show error message" rule can stop this create.
    If the create succeeds, the probe record is deleted again.
    """
    code = "PR-PROBE-" + str(budget)
    body = {"mgl_name": "custkit probe (safe to delete)", "mgl_budget": budget}
    entity_set = cfg["entity_set"]
    try:
        r = api.request("PATCH", f"{entity_set}(mgl_requestcode={odata_string(code)})", json=body,
                        headers={"If-None-Match": "*"})        # create-only upsert by the episode 1 alternate key
    except DataverseError as e:
        out(f"server refused: HTTP {e.status}: {e.message}")
        return True
    created = r.headers.get("OData-EntityId", "")
    out(f"server accepted the record without a justification ({created or 'created'})")
    if created:
        api.delete(created)
        out("probe record deleted")
    return False
