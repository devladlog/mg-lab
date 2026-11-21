"""Dataverse Web API payloads for business process flow instances (Learn: Work with business process flows using code).

Pure functions: no network, no secrets. `stage_ids` maps our symbolic stage ids to the processstage GUIDs of the
environment (they differ per environment: read them with the query in scripts/Set-BpfStage.ps1 -ListStages).
"""
from __future__ import annotations

from .engine import Instance

ZERO = "00000000-0000-0000-0000-000000000000"


def traversed_path(instance: Instance, stage_ids: dict[str, str]) -> str:
    """traversedpath: comma-delimited processstage ids of the visited stages."""
    return ",".join(stage_ids[s] for s in instance.traversed)


def bind_stage(stage_guid: str) -> str:
    return f"/processstages({stage_guid})"


def create_instance(instance: Instance, stage_ids: dict[str, str], primary_nav: str, primary_set: str,
                    record_id: str) -> dict:
    """POST /<bpf table>. primary_set is the entity set name of the primary table (e.g. cts_purchaserequests). traversedpath is required when the active stage is not the first one."""
    body = {
        f"{primary_nav}@odata.bind": f"/{primary_set}({record_id})",
        "activestageid@odata.bind": bind_stage(stage_ids[instance.active]),
    }
    if instance.active != instance.process.first_stage:
        body["traversedpath"] = traversed_path(instance, stage_ids)
    return body


def move_stage(instance: Instance, stage_ids: dict[str, str]) -> dict:
    """PATCH /<bpf table>(<instance id>): new activestageid plus the updated traversedpath."""
    return {
        "activestageid@odata.bind": bind_stage(stage_ids[instance.active]),
        "traversedpath": traversed_path(instance, stage_ids),
    }


STATE = {
    "abort": {"statecode": 1, "statuscode": 3},
    "reactivate": {"statecode": 0, "statuscode": 1},
    "finish": {"statecode": 0, "statuscode": 2},
}


def change_state(kind: str) -> dict:
    return dict(STATE[kind])
