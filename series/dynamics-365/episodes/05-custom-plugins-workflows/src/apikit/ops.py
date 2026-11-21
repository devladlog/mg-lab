"""Day-two commands: call the custom API, backfill scores, read system jobs and trace logs, inventory classic workflows."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .webapi import DataverseError, WebApi, odata_string

# AsyncOperation.StatusCode (Learn: Asynchronous service > Manage system job states)
JOB_STATUS = {0: "Waiting For Resources", 10: "Waiting", 20: "In Progress", 21: "Pausing", 22: "Canceling",
              30: "Succeeded", 31: "Failed", 32: "Canceled"}
WORKFLOW_CATEGORY = {0: "Workflow", 1: "Dialog", 2: "Business Rule", 3: "Action", 4: "Business Process Flow",
                     5: "Modern Flow", 6: "Desktop Flow", 7: "AI Flow"}
WORKFLOW_MODE = {0: "Background", 1: "Real-time"}


def find_request(api: WebApi, cfg, code: str) -> Dict[str, Any]:
    key = f"{cfg['entity_set']}({cfg['key']}={odata_string(code)})"
    try:
        return api.get(f"{key}?$select={cfg['table']}id,mgl_name,{cfg['column']['schema'].lower()}")
    except DataverseError as e:
        if e.status == 404:
            raise DataverseError(404, "", f"no {cfg['table']} with {cfg['key']} = {code}") from None
        raise


def call_api(api: WebApi, cfg, record_id: str) -> Dict[str, Any]:
    """POST <entityset>(<id>)/Microsoft.Dynamics.CRM.<uniquename>: bound actions need the fully qualified name."""
    name = cfg["custom_api"]["uniquename"]
    r = api.action(f"{cfg['entity_set']}({record_id})/Microsoft.Dynamics.CRM.{name}", {})
    body = r.json()
    return {k: v for k, v in body.items() if not k.startswith("@")}


def cmd_call(api: WebApi, cfg, code: str, out=print) -> Dict[str, Any]:
    rec = find_request(api, cfg, code)
    res = call_api(api, cfg, rec[f"{cfg['table']}id"])
    out(f"{code}  {rec.get('mgl_name', '')}")
    out(f"  RiskScore {res.get('RiskScore')}  RiskLevel {res.get('RiskLevel')}")
    for reason in str(res.get("Reasons", "")).split("; "):
        out(f"   - {reason}")
    stored = rec.get(cfg["column"]["schema"].lower())
    out(f"  stored {cfg['column']['schema'].lower()}: {'(empty)' if stored is None else stored}")
    return res


def cmd_backfill(api: WebApi, cfg, *, apply: bool, out=print) -> int:
    """Records saved before the async step existed have no score. Score them through the same custom API."""
    col = cfg["column"]["schema"].lower()
    rows = list(api.get_all(f"{cfg['entity_set']}?$select={cfg['table']}id,{cfg['key']}"
                            f"&$filter=statecode eq 0 and {col} eq null&$orderby={cfg['key']}"))
    out(f"{len(rows)} active request(s) without {col}")
    failed = 0
    for row in rows:
        rid, code = row[f"{cfg['table']}id"], row.get(cfg["key"], "?")
        try:
            res = call_api(api, cfg, rid)
            if apply:
                api.update(f"{cfg['entity_set']}({rid})", {col: res["RiskScore"]}, in_solution=False)
            out(f"  {'+' if apply else ' '} {code:<8} {res['RiskScore']:>3}  {res['RiskLevel']}")
        except DataverseError as e:
            failed += 1
            out(f"  ! {code:<8} {e}")
    if not apply and rows:
        out("dry run: add --apply to write the scores")
    return 1 if failed else 0


def step_ids(api: WebApi, cfg) -> Dict[str, str]:
    """{step id: step name} for every step of the assembly's plug-in types."""
    asm = api.get(f"pluginassemblies?$select=pluginassemblyid&$filter=name eq {odata_string(cfg['assembly']['name'])}")["value"]
    if not asm:
        return {}
    types = api.get(f"plugintypes?$select=plugintypeid&$filter=_pluginassemblyid_value eq {asm[0]['pluginassemblyid']}")["value"]
    found = {}
    for t in types:
        for s in api.get("sdkmessageprocessingsteps?$select=sdkmessageprocessingstepid,name,asyncautodelete"
                         f"&$filter=_eventhandler_value eq {t['plugintypeid']}")["value"]:
            found[s["sdkmessageprocessingstepid"]] = s["name"] + (" [auto-delete on success]" if s.get("asyncautodelete") else "")
    return found


def cmd_jobs(api: WebApi, cfg, *, failed_only: bool, top: int = 10, out=print) -> int:
    """System jobs (asyncoperation) created by our async steps. Learn's query: _owningextensionid_value eq <step id>."""
    steps = step_ids(api, cfg)
    if not steps:
        out("no steps registered: run deploy first")
        return 1
    failures = 0
    for sid, name in steps.items():
        flt = f"_owningextensionid_value eq {sid}" + (" and statuscode eq 31" if failed_only else "")
        jobs = api.get(f"asyncoperations?$select=name,statuscode,friendlymessage,message,createdon,completedon,"
                       f"_regardingobjectid_value&$filter={flt}&$orderby=createdon desc&$top={top}")["value"]
        out(f"{name}: {len(jobs)} job(s)")
        for j in jobs:
            status = JOB_STATUS.get(j.get("statuscode"), str(j.get("statuscode")))
            out(f"  {j.get('createdon', '')[:19]}  {status:<22} {j.get('friendlymessage') or ''}".rstrip())
            if j.get("statuscode") == 31:
                failures += 1
                out(f"     {first_line(j.get('message'))}")
    out("note: steps with auto-delete keep only failed or unfinished jobs; succeeded ones are deleted")
    return 1 if failures else 0


def first_line(text: Optional[str], width: int = 110) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= width else line[: width - 3] + "..."


def cmd_trace(api: WebApi, cfg, *, top: int = 10, out=print) -> int:
    """Plug-in trace log rows for our classes. Learn filters with startswith(typename,'<namespace>.<class>').
    Needs trace logging on (Settings > Administration > System Settings > Customization)."""
    rows = api.get("plugintracelogs?$select=createdon,typename,messagename,mode,depth,performanceexecutionduration,"
                   "messageblock,exceptiondetails"
                   f"&$filter=startswith(typename,{odata_string(cfg['assembly']['name'] + '.')})&$orderby=createdon desc&$top={top}")["value"]
    if not rows:
        out("no trace rows: is plug-in trace logging set to All (or Exception)? Rows are deleted after 24 hours.")
        return 1
    for r in rows:
        short = (r.get("typename") or "").split(",")[0].rsplit(".", 1)[-1]
        mode = "async" if r.get("mode") == 1 else "sync"
        out(f"{r.get('createdon', '')[:19]}  {short:<24} {r.get('messagename', ''):<26} {mode:<5} "
            f"depth {r.get('depth')}  {r.get('performanceexecutionduration')} ms")
        for line in (r.get("messageblock") or "").strip().splitlines()[-3:]:
            out(f"    {line}")
        if r.get("exceptiondetails"):
            out(f"    ! {first_line(r['exceptiondetails'])}")
    return 0


def migration_hint(row: Dict[str, Any]) -> str:
    """Where a classic process should go. Based on Learn: 'Replace classic workflows with flows' and
    'custom APIs are an alternative to custom process actions'."""
    cat, mode = row.get("category"), row.get("mode")
    if cat == 3:
        return "custom API (code) - or keep the action if makers maintain it"
    if cat == 0 and mode == 1:
        return "real-time: a synchronous plug-in, a business rule or Power Fx; ask if it can be async"
    if cat == 0:
        triggers = [t for t, on in (("create", row.get("triggeroncreate")), ("delete", row.get("triggerondelete")),
                                    ("update", bool(row.get("triggeronupdateattributelist")))) if on]
        if not triggers and row.get("ondemand"):
            return "cloud flow with 'When a row is selected' (on demand)"
        return f"cloud flow, Dataverse trigger on {'/'.join(triggers) or '?'}" + (
            f" (columns {row['triggeronupdateattributelist']})" if row.get("triggeronupdateattributelist") else "")
    return "-"


def workflow_rows(api: WebApi, *, include_managed: bool, table: Optional[str]) -> List[Dict[str, Any]]:
    flt = "(category eq 0 or category eq 3) and type eq 1"
    if not include_managed:
        flt += " and ismanaged eq false"
    if table:
        flt += f" and primaryentity eq {odata_string(table)}"
    return list(api.get_all("workflows?$select=name,category,mode,primaryentity,statecode,triggeroncreate,"
                            "triggerondelete,triggeronupdateattributelist,ondemand,scope,ismanaged"
                            f"&$filter={flt}&$orderby=primaryentity,name"))


def cmd_workflows(api: WebApi, *, include_managed: bool, table: Optional[str], out=print) -> int:
    rows = workflow_rows(api, include_managed=include_managed, table=table)
    out(f"{len(rows)} classic workflow(s)/action(s)" + ("" if include_managed else " (unmanaged only; --all for managed)"))
    for r in rows:
        state = "On" if r.get("statecode") == 1 else "Off"
        kind = WORKFLOW_CATEGORY.get(r.get("category"), "?")
        if r.get("category") == 0:
            kind += f" ({WORKFLOW_MODE.get(r.get('mode'), '?')})"
        out(f"  {r.get('primaryentity', ''):<22} {r.get('name', '')[:40]:<40} {kind:<22} {state:<3} -> {migration_hint(r)}")
    return 0
