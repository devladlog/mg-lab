"""Open-case triage against the team's own targets, plus create/resolve helpers for the Case (incident) table.

Case table reference (Learn): prioritycode 1 High / 2 Normal / 3 Low; caseorigincode 1 Phone, 2 Email, 3 Web,
2483 Facebook, 3986 Twitter, 700610000 IoT; casetypecode 1 Question / 2 Problem / 3 Request; statecode 0 Active,
1 Resolved, 2 Cancelled; statuscode 1 In Progress, 2 On Hold, 3 Waiting for Details, 4 Researching, 5 Problem
Solved (state 1), 6 Cancelled, 1000 Information Provided (state 1), 2000 Merged; customerid targets account and
contact; title max 200; ticketnumber is read-only ("cannot be modified").
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .webapi import WebApi, odata_string

FMT = "@OData.Community.Display.V1.FormattedValue"
PRIORITY = {1: "High", 2: "Normal", 3: "Low"}
SELECT = ("incidentid,ticketnumber,title,prioritycode,caseorigincode,statuscode,createdon,firstresponsesent,"
          "isescalated,_customerid_value")
STATE_ACTIVE = 0
STATUS_PROBLEM_SOLVED, STATUS_INFO_PROVIDED = 5, 1000


@dataclass
class Case:
    id: str
    number: str
    title: str
    customer: str
    priority: int
    created: dt.datetime
    first_response_sent: bool
    escalated: bool
    status: int

    def age_hours(self, now: dt.datetime) -> float:
        return (now - self.created).total_seconds() / 3600


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def to_case(row: Dict[str, Any]) -> Case:
    return Case(id=row.get("incidentid", ""), number=row.get("ticketnumber") or "", title=row.get("title") or "",
                customer=row.get("_customerid_value" + FMT) or "(no customer)",
                priority=int(row.get("prioritycode") or 2), created=parse_time(row["createdon"]),
                first_response_sent=bool(row.get("firstresponsesent")), escalated=bool(row.get("isescalated")),
                status=int(row.get("statuscode") or 1))


def fetch_open(api: WebApi) -> List[Case]:
    path = f"incidents?$select={SELECT}&$filter=statecode eq 0&$orderby=createdon asc"
    return [to_case(r) for r in api.get_all(path, annotations=True)]


@dataclass
class Finding:
    level: str
    code: str
    case: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():<7} {self.code}  {self.case}: {self.message}"


def triage(cases: Iterable[Case], now: dt.datetime, cfg: Dict[str, Any]) -> List[Finding]:
    out: List[Finding] = []
    for c in cases:
        p = str(c.priority)
        age = c.age_hours(now)
        label = f"{c.number} {c.title}".strip()
        first, resolve = cfg["first_response_hours"][p], cfg["resolve_hours"][p]
        if not c.first_response_sent and age > first:
            out.append(Finding("error", "C002", label, f"no first response after {age:.1f} h (target {first} h, "
                                                       f"{PRIORITY.get(c.priority, c.priority)} priority)"))
        if age > resolve:
            out.append(Finding("error", "C001", label, f"open {age:.0f} h, resolve target {resolve} h"))
        elif age > resolve * cfg["due_soon_ratio"] and c.status != 2:
            out.append(Finding("warning", "C003", label, f"{age / resolve:.0%} of the {resolve} h resolve target used"))
        if c.escalated:
            out.append(Finding("info", "C004", label, "escalated"))
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda f: (order[f.level], f.code, f.case))


def summary(cases: List[Case], now: dt.datetime) -> List[str]:
    lines = [f"{len(cases)} open case(s)", "", f"{'priority':<9} {'open':>4} {'oldest h':>9} {'no 1st reply':>13}"]
    for p in (1, 2, 3):
        cs = [c for c in cases if c.priority == p]
        if cs:
            lines.append(f"{PRIORITY[p]:<9} {len(cs):>4} {max(c.age_hours(now) for c in cs):>9.0f} "
                         f"{sum(not c.first_response_sent for c in cs):>13}")
    return lines


# ---- writes -----------------------------------------------------------------------------------------------

def find_account(api: WebApi, name: str) -> Optional[str]:
    rows = api.get(f"accounts?$select=accountid&$filter=name eq {odata_string(name)}&$top=1")["value"]
    return rows[0]["accountid"] if rows else None


def case_body(title: str, account_id: str, *, priority: int = 2, origin: int = 2, case_type: int = 2,
              description: str = "") -> Dict[str, Any]:
    if not title or len(title) > 200:
        raise ValueError("case title is required and is at most 200 characters")
    if priority not in PRIORITY:
        raise ValueError("priority must be 1 (High), 2 (Normal) or 3 (Low)")
    body: Dict[str, Any] = {"title": title, "prioritycode": priority, "caseorigincode": origin,
                            "casetypecode": case_type, "customerid_account@odata.bind": f"/accounts({account_id})"}
    if description:
        body["description"] = description
    return body


def seed(api: WebApi, specs: List[Dict[str, Any]], cfg: Dict[str, Any], *, apply: bool = False,
         out=print) -> int:
    """Create the demo cases that don't exist yet (matched by title). ticketnumber is set by the system."""
    account_id = find_account(api, cfg["demo_account"])
    if not account_id:
        raise ValueError(f"account '{cfg['demo_account']}' not found: qualify the lead from episode 7 first")
    created = 0
    for s in specs:
        title = cfg["demo_prefix"] + s["title"]
        exists = api.get(f"incidents?$select=incidentid&$filter=title eq {odata_string(title)}&$top=1")["value"]
        if exists:
            out(f"= {title}")
            continue
        body = case_body(title, account_id, priority=s.get("priority", 2), origin=s.get("origin", 2),
                         case_type=s.get("type", 2), description=s.get("description", ""))
        out(f"+ {title}" + ("" if apply else "  (dry run)"))
        if apply:
            api.post("incidents", body)
        created += 1
    return created


def resolve_body(case_id: str, subject: str, description: str = "", status: int = STATUS_PROBLEM_SOLVED
                 ) -> Dict[str, Any]:
    if status not in (STATUS_PROBLEM_SOLVED, STATUS_INFO_PROVIDED):
        raise ValueError("resolving uses status reason 5 (Problem Solved) or 1000 (Information Provided)")
    res: Dict[str, Any] = {"@odata.type": "Microsoft.Dynamics.CRM.incidentresolution", "subject": subject,
                           "incidentid@odata.bind": f"/incidents({case_id})"}
    if description:
        res["description"] = description
    return {"IncidentResolution": res, "Status": status}


def resolve(api: WebApi, case_id: str, subject: str = "Case resolved", description: str = "",
            status: int = STATUS_PROBLEM_SOLVED, *, apply: bool = False, out=print) -> Dict[str, Any]:
    case = api.get(f"incidents({case_id})?$select=ticketnumber,title,statecode,statuscode")
    if case.get("statecode") != STATE_ACTIVE:
        raise ValueError(f"{case.get('ticketnumber')} is not active (statecode {case.get('statecode')})")
    payload = resolve_body(case_id, subject, description, status)
    out(f"{case.get('ticketnumber')} {case.get('title')}: CloseIncident status {status}")
    if not apply:
        out("dry run: add --apply to resolve")
        return {}
    api.post("CloseIncident", payload)
    res = api.get(f"incidents({case_id})?$select=statecode,statuscode")
    out(f"now statecode {res.get('statecode')} statuscode {res.get('statuscode')} (1 / 5 = Resolved, Problem Solved)")
    return res
