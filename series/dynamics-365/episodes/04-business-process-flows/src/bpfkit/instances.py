"""Process instances: read, create, move one stage, finish or abandon. All requests follow
"Work with business process flows using code" (Power Automate docs) and the Web API function references.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import path
from .definition import BpfDefinition
from .webapi import DataverseError, WebApi, odata_string


@dataclass
class Instance:
    id: str
    stage_id: str
    traversed: str
    statecode: Optional[int]
    statuscode: Optional[int]
    stage_started: Optional[str] = None
    record_id: str = ""

    @property
    def state(self) -> str:
        return path.state_name(self.statecode, self.statuscode)

    @property
    def active(self) -> bool:
        return (self.statecode, self.statuscode) == path.ACTIVE


INSTANCE_SELECT = "businessprocessflowinstanceid,_activestageid_value,traversedpath,statecode,statuscode,activestagestartedon"


def to_instance(row: Dict[str, Any], d: BpfDefinition) -> Instance:
    return Instance(id=path.norm(row["businessprocessflowinstanceid"]), stage_id=path.norm(row.get("_activestageid_value")),
                    traversed=row.get("traversedpath") or "", statecode=row.get("statecode"),
                    statuscode=row.get("statuscode"), stage_started=row.get("activestagestartedon"),
                    record_id=path.norm(row.get(d.lookup_value)))


def find_record(api: WebApi, entity_set: str, key: str, code: str, table: str) -> Dict[str, Any]:
    """By alternate key (episode 1): mgl_projectrequests(mgl_requestcode='PR-0004')."""
    try:
        return api.get(f"{entity_set}({key}={odata_string(code)})?$select={table}id,mgl_name")
    except DataverseError as e:
        if e.status == 404:
            raise DataverseError(404, "RecordNotFound", f"no {table} with {key} = {code}") from None
        raise


def instances_for(api: WebApi, d: BpfDefinition, record_id: str) -> List[Instance]:
    """This BPF's instances for one record, most recently modified first (that's the one the form shows)."""
    rows = api.get(f"{d.entity_set}?$select={INSTANCE_SELECT},{d.lookup_value}"
                   f"&$filter={d.lookup_value} eq {path.norm(record_id)}&$orderby=modifiedon desc")["value"]
    return [to_instance(r, d) for r in rows]


def all_processes_for(api: WebApi, table: str, record_id: str) -> List[Dict[str, Any]]:
    """RetrieveProcessInstances: instances of EVERY BPF on the record, most recently modified first.
    Each row carries the active stage id in `processstageid` (Learn)."""
    return api.get("RetrieveProcessInstances(EntityLogicalName=@p1,EntityId=@p2)"
                   f"?@p1={odata_string(table)}&@p2={path.norm(record_id)}")["value"]


def active_path(api: WebApi, instance_id: str) -> List[Dict[str, Any]]:
    """RetrieveActivePath: completed stages, the active stage and the predicted future stages, evaluated with the
    branch conditions against the record's current data. This is the only reliable stage order."""
    return api.get(f"RetrieveActivePath(ProcessInstanceId=@p1)?@p1={path.norm(instance_id)}")["value"]


def path_ids(stages: List[Dict[str, Any]]) -> List[str]:
    return [path.norm(s["processstageid"]) for s in stages]


def move(api: WebApi, d: BpfDefinition, inst: Instance, direction: str, *, dry_run: bool = False) -> path.Move:
    if not inst.active:
        raise path.StageMoveError(f"instance is {inst.state}: reactivate it before moving stages")
    ap = path_ids(active_path(api, inst.id))
    mv = path.forward(ap, inst.stage_id, inst.traversed) if direction == "next" else \
        path.back(ap, inst.stage_id, inst.traversed)
    if not dry_run:
        api.update(f"{d.entity_set}({inst.id})", mv.payload(), in_solution=False)
    return mv


def finish(api: WebApi, d: BpfDefinition, inst: Instance) -> None:
    ap = path_ids(active_path(api, inst.id))
    if not path.can_finish(ap, inst.stage_id):
        raise path.StageMoveError(f"can only finish at the last stage ({d.stage_name(ap[-1]) if ap else '?'}); "
                                  f"active stage is {d.stage_name(inst.stage_id)}")
    api.update(f"{d.entity_set}({inst.id})", {"statecode": 0, "statuscode": 2}, in_solution=False)


def abandon(api: WebApi, d: BpfDefinition, inst: Instance) -> None:
    api.update(f"{d.entity_set}({inst.id})", {"statecode": 1, "statuscode": 3}, in_solution=False)


def reactivate(api: WebApi, d: BpfDefinition, inst: Instance) -> None:
    api.update(f"{d.entity_set}({inst.id})", {"statecode": 0, "statuscode": 1}, in_solution=False)


def create(api: WebApi, d: BpfDefinition, entity_set: str, record_id: str, first_stage_id: str) -> str:
    """POST an instance at the first stage: lookup to the record + active stage, both with @odata.bind."""
    # Learn's example sends only the two binds for the first stage; traversedpath is required only when the
    # instance starts at a later stage.
    body = {f"{d.nav}@odata.bind": f"/{entity_set}({path.norm(record_id)})",
            "activestageid@odata.bind": f"/processstages({path.norm(first_stage_id)})"}
    return api.create(d.entity_set, body, in_solution=False)
