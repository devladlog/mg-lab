"""Find a business process flow definition and everything code needs to work with its instances.

- The definition is a `workflow` row with category 4 (Business Process Flow); statecode 1 = Activated.
- Activating it creates a table for its instances named <prefix>_<uniquename>; `workflow.uniquename` is that
  logical name. We read its EntitySetName from metadata instead of guessing the plural.
- The lookup from the instance table to our record (e.g. bpf_mgl_projectrequestid) and its navigation property
  are read from the table's ManyToOne relationships: Learn says to look the navigation property up, not assume it.
- Stages are `processstage` rows. Don't trust their order: Learn's own example returns S1, S3, S2.
  The order a record actually follows comes from RetrieveActivePath.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .path import norm
from .webapi import DataverseError, WebApi, odata_string

CATEGORY_BPF = 4
STATE_ACTIVATED = 1


@dataclass
class Stage:
    id: str
    name: str
    entity: str = ""


@dataclass
class BpfDefinition:
    workflow_id: str
    name: str
    unique_name: str          # = logical name of the instance table
    primary_entity: str
    activated: bool
    entity_set: str = ""      # instance table entity set, e.g. mgl_projectapprovals
    lookup: str = ""          # instance -> record lookup column, e.g. bpf_mgl_projectrequestid
    nav: str = ""             # its single-valued navigation property (for @odata.bind)
    stages: List[Stage] = field(default_factory=list)

    @property
    def lookup_value(self) -> str:
        return f"_{self.lookup}_value"

    def stage_name(self, stage_id: str) -> str:
        sid = norm(stage_id)
        return next((s.name for s in self.stages if s.id == sid), sid or "?")

    def stage_id(self, name: str) -> str:
        for s in self.stages:
            if s.name.lower() == name.lower():
                return s.id
        raise KeyError(f"no stage named {name!r} (stages: {', '.join(s.name for s in self.stages)})")

    def names(self) -> Dict[str, str]:
        return {s.id: s.name for s in self.stages}


def load(api: WebApi, bpf_name: str, table: str) -> BpfDefinition:
    rows = api.get("workflows?$select=workflowid,name,uniquename,primaryentity,statecode"
                   f"&$filter=category eq {CATEGORY_BPF} and name eq {odata_string(bpf_name)}")["value"]
    if not rows:
        raise DataverseError(404, "BpfNotFound", f"no business process flow named {bpf_name!r}")
    w = rows[0]
    d = BpfDefinition(workflow_id=norm(w["workflowid"]), name=w["name"], unique_name=w.get("uniquename") or "",
                      primary_entity=w.get("primaryentity") or "", activated=w.get("statecode") == STATE_ACTIVATED)
    if d.primary_entity and d.primary_entity != table:
        raise DataverseError(400, "WrongTable", f"{bpf_name!r} starts on {d.primary_entity}, not {table}")
    if not d.activated or not d.unique_name:
        raise DataverseError(409, "BpfNotActivated",
                             f"{bpf_name!r} is a draft: activate it first (its instance table is created on activation)")

    meta = api.get(f"EntityDefinitions(LogicalName='{d.unique_name}')?$select=EntitySetName,IsBPFEntity")
    if meta.get("IsBPFEntity") is False:
        raise DataverseError(400, "NotBpfTable", f"{d.unique_name} isn't a business process flow table")
    d.entity_set = meta["EntitySetName"]

    rels = api.get(f"EntityDefinitions(LogicalName='{d.unique_name}')/ManyToOneRelationships"
                   "?$select=ReferencedEntity,ReferencingAttribute,ReferencingEntityNavigationPropertyName")["value"]
    to_table = [r for r in rels if r.get("ReferencedEntity") == table]
    if not to_table:
        raise DataverseError(404, "NoLookup", f"{d.unique_name} has no lookup to {table}")
    # Prefer the bpf_ lookup the platform creates for the stage table.
    rel = next((r for r in to_table if r["ReferencingAttribute"].startswith("bpf_")), to_table[0])
    d.lookup, d.nav = rel["ReferencingAttribute"], rel["ReferencingEntityNavigationPropertyName"]

    stages = api.get("processstages?$select=processstageid,stagename,primaryentitytypecode"
                     f"&$filter=processid/workflowid eq {d.workflow_id}")["value"]
    d.stages = [Stage(norm(s["processstageid"]), s["stagename"], s.get("primaryentitytypecode") or "") for s in stages]
    return d
