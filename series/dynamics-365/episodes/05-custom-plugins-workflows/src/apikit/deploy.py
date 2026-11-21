"""deploy / remove: register everything in plugins.json, idempotently, inside the solution.

Order matters: column -> assembly -> plug-in types -> custom API (needs the main-operation type) -> steps + images.
A second run changes nothing and says so. Immutable custom API properties are refused, not silently ignored.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import registration as reg
from .webapi import DataverseError, WebApi, odata_string


@dataclass
class Report:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"{len(self.created)} created, {len(self.updated)} updated, {len(self.unchanged)} unchanged"


def _one(api: WebApi, path: str) -> Optional[Dict[str, Any]]:
    rows = api.get(path).get("value", [])
    return rows[0] if rows else None


def ensure_column(api: WebApi, cfg, rep: Report, out: Callable[[str], None]) -> None:
    logical = cfg["column"]["schema"].lower()
    path = f"EntityDefinitions(LogicalName='{cfg['table']}')/Attributes(LogicalName='{logical}')"
    if api.exists(path):
        rep.unchanged.append(f"column {logical}")
        return
    api.create(f"EntityDefinitions(LogicalName='{cfg['table']}')/Attributes", reg.integer_column(cfg["column"]))
    rep.created.append(f"column {logical}")
    out(f"+ column {logical} (whole number {cfg['column']['min']}-{cfg['column']['max']})")


def ensure_assembly(api: WebApi, cfg, dll: bytes, rep: Report, out) -> str:
    name = cfg["assembly"]["name"]
    found = _one(api, f"pluginassemblies?$select=pluginassemblyid,version,content&$filter=name eq {odata_string(name)}")
    body = reg.assembly_body(name, dll)
    if found is None:
        aid = api.create("pluginassemblies", body)
        rep.created.append(f"assembly {name}")
        out(f"+ assembly {name} ({len(dll):,} bytes, sandbox, database)")
        return aid
    aid = found["pluginassemblyid"]
    if found.get("content") == body["content"]:
        rep.unchanged.append(f"assembly {name}")
        return aid
    if found.get("version") and found["version"].split(".")[:2] != cfg["assembly"]["version"].split(".")[:2]:
        raise DataverseError(409, "version", f"{name} is {found['version']} on the server and "
                             f"{cfg['assembly']['version']} here: a major/minor change is a different assembly "
                             "(Learn: assembly versioning). Register it side by side and move the steps.")
    api.update(f"pluginassemblies({aid})", {"content": body["content"]})
    rep.updated.append(f"assembly {name}")
    out(f"~ assembly {name}: new content (sha256 {hashlib.sha256(dll).hexdigest()[:12]})")
    return aid


def ensure_types(api: WebApi, cfg, assembly_id: str, rep: Report, out) -> Dict[str, str]:
    ids = {}
    for t in cfg["plugin_types"]:
        found = _one(api, f"plugintypes?$select=plugintypeid&$filter=typename eq {odata_string(t['typename'])}"
                          f" and _pluginassemblyid_value eq {assembly_id}")
        if found:
            ids[t["typename"]] = found["plugintypeid"]
            rep.unchanged.append(f"type {t['typename']}")
        else:
            ids[t["typename"]] = api.create("plugintypes", reg.plugintype_body(assembly_id, t["typename"], t["friendlyname"]))
            rep.created.append(f"type {t['typename']}")
            out(f"+ plug-in type {t['typename']}")
    return ids


API_SELECT = ("customapis?$select=customapiid,uniquename,name,displayname,description,bindingtype,"
              "boundentitylogicalname,isfunction,isprivate,allowedcustomprocessingsteptype,workflowsdkstepenabled,"
              "executeprivilegename,_plugintypeid_value"
              "&$expand=CustomAPIResponseProperties($select=uniquename,type,logicalentityname),"
              "CustomAPIRequestParameters($select=uniquename,type,logicalentityname,isoptional)"
              "&$filter=uniquename eq ")


def ensure_custom_api(api: WebApi, cfg, type_ids: Dict[str, str], rep: Report, out) -> str:
    c = cfg["custom_api"]
    desired = reg.custom_api_body(cfg, type_ids[c["plugintype"]])
    found = _one(api, API_SELECT + odata_string(c["uniquename"]))
    if found is None:
        cid = api.create("customapis", desired)
        rep.created.append(f"custom API {c['uniquename']}")
        out(f"+ custom API {c['uniquename']} ({len(desired['CustomAPIResponseProperties'])} response properties)")
        return cid
    cid = found["customapiid"]
    patch, conflicts, add, extra = reg.diff_custom_api(found, desired)
    if conflicts:
        raise DataverseError(409, "immutable", "custom API properties that can't change after creation differ: "
                             + "; ".join(conflicts) + ". Delete the custom API and deploy again.")
    if found.get("_plugintypeid_value") != type_ids[c["plugintype"]]:
        patch["PluginTypeId@odata.bind"] = desired["PluginTypeId@odata.bind"]
    for p in add:
        api.create("customapiresponseproperties", {**p, "CustomAPIId@odata.bind": f"/customapis({cid})"})
        out(f"+ response property {p['uniquename']}")
    for name in extra:
        out(f"! response property {name} exists on the server but not in plugins.json (left alone)")
    if patch:
        api.update(f"customapis({cid})", patch)
        out(f"~ custom API {c['uniquename']}: {', '.join(k.split('@')[0] for k in patch)}")
    (rep.updated if patch or add else rep.unchanged).append(f"custom API {c['uniquename']}")
    return cid


def _message_and_filter(api: WebApi, message: str, table: str):
    msg = _one(api, f"sdkmessages?$select=sdkmessageid&$filter=name eq {odata_string(message)}")
    if msg is None:
        raise DataverseError(404, "", f"no sdkmessage {message}")
    flt = _one(api, f"sdkmessagefilters?$select=sdkmessagefilterid&$filter=primaryobjecttypecode eq "
                    f"{odata_string(table)} and _sdkmessageid_value eq {msg['sdkmessageid']}")
    if flt is None:
        raise DataverseError(404, "", f"{message} isn't available for {table}")
    return msg["sdkmessageid"], flt["sdkmessagefilterid"]


def ensure_steps(api: WebApi, cfg, type_ids: Dict[str, str], rep: Report, out) -> List[str]:
    step_ids = []
    for s in cfg["steps"]:
        tid = type_ids[s["plugintype"]]
        mid, fid = _message_and_filter(api, s["message"], cfg["table"])
        desired = reg.step_body(s, cfg["table"], tid, mid, fid)
        label = f"step {s['message']} ({reg.STAGES[s['stage']]}, {reg.MODES[s['mode']]})"
        found = _one(api, "sdkmessageprocessingsteps?$select=sdkmessageprocessingstepid,mode,stage,rank,"
                          "asyncautodelete,filteringattributes"
                          f"&$filter=_eventhandler_value eq {tid} and _sdkmessagefilterid_value eq {fid}")
        if found is None:
            sid = api.create("sdkmessageprocessingsteps", desired)
            rep.created.append(label)
            out(f"+ {label}" + (f" filtering {desired['filteringattributes']}" if desired["filteringattributes"] else ""))
        else:
            sid = found["sdkmessageprocessingstepid"]
            changes = reg.step_changes(found, desired)
            if changes:
                api.update(f"sdkmessageprocessingsteps({sid})", changes)
                rep.updated.append(label)
                out(f"~ {label}: {', '.join(changes)}")
            else:
                rep.unchanged.append(label)
        step_ids.append(sid)
        if s.get("post_image"):
            ensure_post_image(api, sid, s["post_image"], label, rep, out)
    return step_ids


def ensure_post_image(api: WebApi, step_id: str, attributes: List[str], label: str, rep: Report, out) -> None:
    found = _one(api, "sdkmessageprocessingstepimages?$select=sdkmessageprocessingstepimageid,attributes"
                      f"&$filter=_sdkmessageprocessingstepid_value eq {step_id} and entityalias eq 'PostImage'")
    want = ",".join(attributes)
    if found is None:
        api.create("sdkmessageprocessingstepimages", reg.post_image_body(step_id, attributes))
        rep.created.append(f"post-image of {label}")
        out(f"+ post-image ({want}) on {label}")
    elif found.get("attributes") != want:
        api.update(f"sdkmessageprocessingstepimages({found['sdkmessageprocessingstepimageid']})", {"attributes": want})
        rep.updated.append(f"post-image of {label}")
    else:
        rep.unchanged.append(f"post-image of {label}")


def deploy(api: WebApi, cfg: Dict[str, Any], dll: bytes, out=print) -> Report:
    problems = reg.validate(cfg)
    if problems:
        raise reg.ConfigError("plugins.json: " + "; ".join(problems))
    rep = Report()
    ensure_column(api, cfg, rep, out)
    aid = ensure_assembly(api, cfg, dll, rep, out)
    types = ensure_types(api, cfg, aid, rep, out)
    ensure_custom_api(api, cfg, types, rep, out)
    ensure_steps(api, cfg, types, rep, out)
    out(rep.summary())
    return rep


def remove(api: WebApi, cfg: Dict[str, Any], out=print) -> int:
    """Tear-down in reverse order. Keeps the mgl_riskscore column: it holds data (delete it in the maker portal)."""
    removed = 0
    asm = _one(api, f"pluginassemblies?$select=pluginassemblyid&$filter=name eq {odata_string(cfg['assembly']['name'])}")
    types = []
    if asm:
        types = api.get(f"plugintypes?$select=plugintypeid,typename&$filter=_pluginassemblyid_value eq "
                        f"{asm['pluginassemblyid']}").get("value", [])
    for t in types:
        for st in api.get("sdkmessageprocessingsteps?$select=sdkmessageprocessingstepid,name"
                          f"&$filter=_eventhandler_value eq {t['plugintypeid']}").get("value", []):
            api.delete(f"sdkmessageprocessingsteps({st['sdkmessageprocessingstepid']})")
            out(f"- step {st['name']}")
            removed += 1
    found = _one(api, f"customapis?$select=customapiid&$filter=uniquename eq {odata_string(cfg['custom_api']['uniquename'])}")
    if found:
        api.delete(f"customapis({found['customapiid']})")
        out(f"- custom API {cfg['custom_api']['uniquename']}")
        removed += 1
    for t in types:
        api.delete(f"plugintypes({t['plugintypeid']})")
        out(f"- plug-in type {t['typename']}")
        removed += 1
    if asm:
        api.delete(f"pluginassemblies({asm['pluginassemblyid']})")
        out(f"- assembly {cfg['assembly']['name']}")
        removed += 1
    out(f"{removed} removed (column {cfg['column']['schema'].lower()} kept)")
    return removed


def read_dll(episode: Path, cfg) -> bytes:
    p = episode / cfg["assembly"]["dll"]
    if not p.exists():
        raise SystemExit(f"{p} not found: dotnet build src/MGLab.D365.Plugins -c Release (with your .snk) first")
    return p.read_bytes()
