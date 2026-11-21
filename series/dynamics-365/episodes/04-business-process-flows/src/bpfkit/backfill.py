"""Records created BEFORE the business process flow was activated have no instance, so they show no process bar.
(Learn: new records get a BPF by the default logic when they're created; nothing is applied retroactively.)

backfill lists active records of the table that have no instance of this BPF and, with apply=True, creates one
at the first stage for each. The first stage is configured by name and cross-checked against the traversed
paths of existing instances, because processstage rows come back in no guaranteed order.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from . import instances, path
from .definition import BpfDefinition
from .webapi import DataverseError, WebApi


@dataclass
class BackfillPlan:
    first_stage_id: str
    missing: List[Dict[str, str]] = field(default_factory=list)   # [{"id":..., "code":...}]
    created: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def check_first_stage(d: BpfDefinition, configured_name: str, traversed_paths: List[str]) -> str:
    sid = d.stage_id(configured_name)
    firsts = Counter(path.parse_traversed(t)[0] for t in traversed_paths if path.parse_traversed(t))
    if firsts and sid not in firsts:
        seen = ", ".join(d.stage_name(s) for s in firsts)
        raise ValueError(f"configured first stage {configured_name!r} but existing instances start at: {seen}")
    return sid


def plan(api: WebApi, d: BpfDefinition, cfg: Dict) -> BackfillPlan:
    table, key = cfg["table"], cfg["key"]
    existing = list(api.get_all(f"{d.entity_set}?$select={d.lookup_value},traversedpath"))
    first = check_first_stage(d, cfg["first_stage"], [r.get("traversedpath") or "" for r in existing])
    have = {path.norm(r.get(d.lookup_value)) for r in existing}
    p = BackfillPlan(first)
    for rec in api.get_all(f"{cfg['entity_set']}?$select={table}id,{key}&$filter=statecode eq 0&$orderby={key}"):
        rid = path.norm(rec[f"{table}id"])
        if rid not in have:
            p.missing.append({"id": rid, "code": rec.get(key) or rid})
    return p


def apply(api: WebApi, d: BpfDefinition, cfg: Dict, p: BackfillPlan, out: Callable[[str], None] = print) -> BackfillPlan:
    for rec in p.missing:
        try:
            instances.create(api, d, cfg["entity_set"], rec["id"], p.first_stage_id)
            p.created.append(rec["code"])
            out(f"  + {rec['code']}: instance at {d.stage_name(p.first_stage_id)}")
        except DataverseError as e:     # keep going: one bad record shouldn't stop the rest
            p.failed.append(rec["code"])
            out(f"  ! {rec['code']}: {e}")
    return p
