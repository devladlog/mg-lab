"""Close an opportunity as won or lost with the WinOpportunity / LoseOpportunity actions.

Learn: closing creates an OpportunityClose activity (actual revenue, close date, competitor, description); the
opportunity's statecode becomes 1 (Won) or 2 (Lost); status reasons 3 Won, 4 Canceled, 5 Out-Sold. The Sales Hub
form says the forecast category is then set to Won or Lost automatically.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from .webapi import WebApi

STATE = {0: "Open", 1: "Won", 2: "Lost"}
STATUS_WON, STATUS_CANCELED, STATUS_OUTSOLD = 3, 4, 5
CHECK = "statecode,statuscode,actualvalue,actualclosedate,msdyn_forecastcategory,name"


def close_body(opportunity_id: str, *, won: bool, revenue: Optional[float], when: dt.datetime,
               description: str = "", competitor_id: Optional[str] = None, status: Optional[int] = None
               ) -> Dict[str, Any]:
    if revenue is not None and revenue < 0:
        raise ValueError("actual revenue can't be negative")
    close: Dict[str, Any] = {
        "@odata.type": "Microsoft.Dynamics.CRM.opportunityclose",
        "subject": "Won by salesctl" if won else "Lost by salesctl",
        "opportunityid@odata.bind": f"/opportunities({opportunity_id})",
        "actualend": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if revenue is not None:
        close["actualrevenue"] = revenue
    if description:
        close["description"] = description
    if competitor_id:
        close["competitorid@odata.bind"] = f"/competitors({competitor_id})"
    if status is None:
        status = STATUS_WON if won else (STATUS_OUTSOLD if competitor_id else STATUS_CANCELED)
    if won and status != STATUS_WON:
        raise ValueError("a won opportunity uses status reason 3 (Won) unless you added custom win reasons")
    return {"Status": status, "OpportunityClose": close}


def close(api: WebApi, opportunity_id: str, *, won: bool, revenue: Optional[float] = None,
          when: Optional[dt.datetime] = None, description: str = "", competitor_id: Optional[str] = None,
          apply: bool = False, out=print) -> Dict[str, Any]:
    opp = api.get(f"opportunities({opportunity_id})?$select={CHECK}", annotations=True)
    if opp.get("statecode") != 0:
        raise ValueError(f"'{opp.get('name')}' is already {STATE.get(opp.get('statecode'), '?')}")
    payload = close_body(opportunity_id, won=won, revenue=revenue, when=when or dt.datetime.now(dt.timezone.utc),
                         description=description, competitor_id=competitor_id)
    action = "WinOpportunity" if won else "LoseOpportunity"
    out(f"'{opp.get('name')}': {action} status {payload['Status']}"
        + (f", actual revenue {revenue:,.0f}" if revenue is not None else ""))
    if not apply:
        out("dry run: add --apply to close")
        return {}
    api.post(action, payload)
    res = api.get(f"opportunities({opportunity_id})?$select={CHECK}", annotations=True)
    out(f"now {STATE.get(res.get('statecode'), '?')} (statuscode {res.get('statuscode')}), actual revenue "
        f"{res.get('actualvalue')}, forecast category "
        f"{res.get('msdyn_forecastcategory@OData.Community.Display.V1.FormattedValue', res.get('msdyn_forecastcategory'))}")
    return res
