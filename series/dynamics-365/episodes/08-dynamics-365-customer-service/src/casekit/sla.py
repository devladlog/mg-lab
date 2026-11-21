"""What the platform's SLA engine says about each open case: the two KPI lookups on the case.

Learn (Create enhanced SLAs): for the Case table the SLA KPI lookup columns refer to the SLA KPI Instance table, and
Learn's troubleshooting page says the case's *First Response By* and *Resolve By* date columns are NOT filled by
default in Unified Interface SLAs. So the status comes from the KPI instance (status, warning time, failure time).
SLAKPIInstance.status: 0 In Progress, 1 Noncompliant, 2 Nearing Noncompliance, 3 Paused, 4 Succeeded, 5 Canceled.
The lookup names (firstresponsebykpiid, resolvebykpiid) are NOT confirmed on Learn: `doctor` lists what the
environment really has, and this module reports a clear hint when the $expand is refused.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .webapi import DataverseError, WebApi

KPI_STATUS = {0: "In Progress", 1: "Noncompliant", 2: "Nearing Noncompliance", 3: "Paused", 4: "Succeeded",
              5: "Canceled"}
FMT = "@OData.Community.Display.V1.FormattedValue"
KPIS = ("firstresponsebykpiid", "resolvebykpiid")
KPI_SELECT = "status,warningtime,failuretime,succeededon"


def query(kpis=KPIS) -> str:
    exp = ",".join(f"{k}($select={KPI_SELECT})" for k in kpis)
    return ("incidents?$select=ticketnumber,title,prioritycode&$filter=statecode eq 0&"
            f"$expand={exp}&$orderby=createdon asc")


def rows(api: WebApi, kpis=KPIS) -> List[Dict[str, Any]]:
    try:
        return list(api.get_all(query(kpis), annotations=True))
    except DataverseError as e:
        if e.status == 400:
            raise DataverseError(e.status, e.code, f"{e.message} (is '{'/'.join(kpis)}' a lookup on the case in this "
                                                   "environment? run `casekit doctor` to list the KPI lookups)") from None
        raise


def report(data: List[Dict[str, Any]], kpis=KPIS) -> List[str]:
    lines = [f"{'case':<14} {'first response':<22} {'resolve':<22} title"]
    bad = 0
    for r in data:
        cells = []
        for k in kpis:
            kpi = r.get(k)
            cells.append("no SLA applied" if not kpi else KPI_STATUS.get(kpi.get("status"), str(kpi.get("status"))))
            bad += bool(kpi and kpi.get("status") in (1, 2))
        lines.append(f"{r.get('ticketnumber', ''):<14} {cells[0]:<22} {cells[1]:<22} {r.get('title', '')}")
    lines.append(f"{len(data)} open case(s), {bad} KPI(s) noncompliant or nearing noncompliance")
    return lines
