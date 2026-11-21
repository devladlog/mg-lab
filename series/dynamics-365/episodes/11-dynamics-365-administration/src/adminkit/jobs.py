"""System jobs (asyncoperation): what failed recently and what looks stuck.

Learn (System Job table reference): statuscode 0 Waiting For Resources, 10 Waiting, 20 In Progress, 21 Pausing,
22 Canceling, 30 Succeeded, 31 Failed, 32 Canceled; statecode 3 = Completed. Text of the error is in friendlymessage
(and message); operationtype is a choice (10 Workflow, 13 Bulk Delete, ...). We ask for formatted values to get its label.
"""
from __future__ import annotations

import datetime as dt
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .findings import Finding
from .webapi import WebApi

FAILED = 31
OPEN_STATUSES = (0, 10, 20)  # waiting for resources, waiting, in progress
SELECT = ("name,operationtype,statuscode,friendlymessage,message,errorcode,createdon,completedon,postponeuntil,"
          "retrycount")
LABEL = "operationtype@OData.Community.Display.V1.FormattedValue"


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def query(now: dt.datetime, window_days: int, stuck_hours: int) -> str:
    """One request for both questions: failed in the window, or still open after stuck_hours."""
    since = iso(now - dt.timedelta(days=window_days))
    cutoff = iso(now - dt.timedelta(hours=stuck_hours))
    opens = " or ".join(f"statuscode eq {s}" for s in OPEN_STATUSES)
    return (f"asyncoperations?$select={SELECT}&$filter=(statuscode eq {FAILED} and completedon ge {since}) "
            f"or (({opens}) and createdon le {cutoff})&$orderby=createdon desc")


def fetch(api: WebApi, now: dt.datetime, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    j = cfg["jobs"]
    return list(api.get_all(query(now, j["window_days"], j["stuck_hours"]), annotations=True))


@dataclass(frozen=True)
class Job:
    name: str
    op_type: str
    status: int
    text: str
    created: Optional[dt.datetime]
    completed: Optional[dt.datetime]
    postpone_until: Optional[dt.datetime]


def to_job(row: Dict[str, Any]) -> Job:
    text = (row.get("friendlymessage") or row.get("message") or "").strip().splitlines()
    first = text[0][:160] if text else "(no message)"
    t = row.get("operationtype")
    return Job(row.get("name") or "(unnamed)", row.get(LABEL) or (f"type {t}" if t is not None else "type ?"),
               row.get("statuscode"), first, parse_time(row.get("createdon")), parse_time(row.get("completedon")),
               parse_time(row.get("postponeuntil")))


def analyse(rows: List[Dict[str, Any]], now: dt.datetime, cfg: Dict[str, Any]) -> List[Finding]:
    """J001 (error): failed jobs in the window, grouped by operation type + message.
    J002 (warning): job still open after stuck_hours and not postponed to the future."""
    window = dt.timedelta(days=cfg["jobs"]["window_days"])
    stuck = dt.timedelta(hours=cfg["jobs"]["stuck_hours"])
    groups: "OrderedDict[tuple, List[Job]]" = OrderedDict()
    out: List[Finding] = []
    for job in (to_job(r) for r in rows):
        if job.status == FAILED:
            if job.completed and now - job.completed <= window:
                groups.setdefault((job.op_type, job.text), []).append(job)
        elif job.status in OPEN_STATUSES and job.created and now - job.created > stuck:
            if job.postpone_until and job.postpone_until > now:
                continue  # waiting on purpose (recurring or delayed job)
            hours = (now - job.created).total_seconds() / 3600
            out.append(Finding("warning", "J002", f"{job.op_type} / {job.name}",
                               f"still open after {hours:.0f} h (status {job.status})"))
    failed = []
    for (op_type, text), jobs in groups.items():
        last = max(j.completed for j in jobs if j.completed)
        failed.append(Finding("error", "J001", op_type, f"{len(jobs)} failed in {window.days} d, last {iso(last)}: {text}"))
    return failed + out


def summary(rows: List[Dict[str, Any]], now: dt.datetime, cfg: Dict[str, Any]) -> List[str]:
    jobs = [to_job(r) for r in rows]
    failed = [j for j in jobs if j.status == FAILED]
    return [f"{len(rows)} job row(s) returned: {len(failed)} failed, {len(jobs) - len(failed)} still open",
            f"window: failed in the last {cfg['jobs']['window_days']} d, open for more than {cfg['jobs']['stuck_hours']} h"]
