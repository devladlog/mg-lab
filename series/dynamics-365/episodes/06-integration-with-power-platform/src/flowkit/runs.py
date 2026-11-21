"""Run history from the Dataverse FlowRun table (solution flows only; kept 28 days by default, Learn).

Columns used (Learn FlowRun reference): name, starttime, endtime, duration (ms), status (Success / Failed /
Cancelled), triggertype, errorcode, errormessage, and the `workflow` lookup (-> _workflow_value).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .webapi import WebApi, odata_string


def find_flow(api: WebApi, name: str, *, with_clientdata: bool = False) -> Dict[str, Any]:
    cols = "workflowid,name,statecode,modifiedon" + (",clientdata" if with_clientdata else "")
    rows = api.get(f"workflows?$select={cols}&$filter=category eq 5 and name eq {odata_string(name)}")["value"]
    if not rows:
        raise LookupError(f"no solution cloud flow named {name!r} (category 5). Flows under My Flows aren't in Dataverse.")
    if len(rows) > 1:
        raise LookupError(f"{len(rows)} cloud flows are named {name!r}: rename one")
    return rows[0]


def fetch(api: WebApi, workflow_id: str, *, days: int, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    since = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return list(api.get_all(
        "flowruns?$select=name,starttime,endtime,duration,status,triggertype,errorcode,errormessage"
        f"&$filter=_workflow_value eq {workflow_id} and starttime ge {since}&$orderby=starttime desc"))


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r.get("status") or "?"] = by_status.get(r.get("status") or "?", 0) + 1
    durations = [r["duration"] for r in rows if isinstance(r.get("duration"), (int, float))]
    failures = [r for r in rows if (r.get("status") or "").lower() == "failed"]
    errors: Dict[str, int] = {}
    for f in failures:
        errors[f.get("errorcode") or "?"] = errors.get(f.get("errorcode") or "?", 0) + 1
    return {"runs": len(rows), "by_status": dict(sorted(by_status.items())),
            "avg_ms": round(sum(durations) / len(durations)) if durations else None,
            "max_ms": max(durations) if durations else None,
            "errors": dict(sorted(errors.items(), key=lambda kv: (-kv[1], kv[0]))),
            "last_failure": failures[0] if failures else None}


def report(name: str, rows: List[Dict[str, Any]], days: int) -> List[str]:
    s = summarize(rows)
    lines = [f"{name}: {s['runs']} run(s) in the last {days} day(s)"]
    if not rows:
        lines.append("  no runs: is the flow on, and is run history in Dataverse enabled (FlowRunTimeToLiveInSeconds > 0)?")
        return lines
    lines.append("  " + "  ".join(f"{k} {v}" for k, v in s["by_status"].items()))
    lines.append(f"  duration avg {s['avg_ms'] / 1000:.1f} s, max {s['max_ms'] / 1000:.1f} s")
    for code, n in s["errors"].items():
        lines.append(f"  error {code} x{n}")
    if s["last_failure"]:
        lf = s["last_failure"]
        lines.append(f"  last failure {lf.get('starttime', '')[:19]}: {(lf.get('errormessage') or '').strip()[:100]}")
    return lines
