"""Qualify a lead with the QualifyLead action instead of clicking Qualify.

Learn (QualifyLeadRequest): creates account, contact and opportunity linked to the lead; with both account and
contact the account becomes the contact's parent customer and the contact the account's primary contact. Learn's
MCP tool page for qualify_lead: repeating qualification is not a safe no-op, so we check state first and verify
the outcome on the lead afterwards (statecode, qualifying opportunity, parent account/contact).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .webapi import DataverseError, WebApi, odata_string

LEAD_OPEN, LEAD_QUALIFIED = 0, 1
STATUS_QUALIFIED = 3  # Learn (qualify_lead): default status reason for a qualified lead
LEAD_SELECT = "leadid,subject,fullname,companyname,emailaddress1,statecode,statuscode"
RESULT_SELECT = ("statecode,statuscode,_qualifyingopportunityid_value,_parentaccountid_value,"
                 "_parentcontactid_value")


def find_open(api: WebApi, email: Optional[str] = None, topic: Optional[str] = None) -> List[Dict[str, Any]]:
    flt = ["statecode eq 0"]
    if email:
        flt.append(f"emailaddress1 eq {odata_string(email)}")
    if topic:
        flt.append(f"contains(subject,{odata_string(topic)})")
    return list(api.get_all(f"leads?$select={LEAD_SELECT}&$filter={' and '.join(flt)}&$orderby=createdon desc"))


def body(account: bool, contact: bool, opportunity: bool, suppress_duplicates: bool = False,
         status: int = STATUS_QUALIFIED) -> Dict[str, Any]:
    if not (account or contact or opportunity):
        raise ValueError("qualifying must create at least one of account, contact, opportunity")
    return {"CreateAccount": account, "CreateContact": contact, "CreateOpportunity": opportunity,
            "SuppressDuplicateDetection": suppress_duplicates, "Status": status}


def qualify(api: WebApi, lead_id: str, *, account: bool = True, contact: bool = True, opportunity: bool = True,
            suppress_duplicates: bool = False, apply: bool = False, out=print) -> Dict[str, Any]:
    lead = api.get(f"leads({lead_id})?$select={LEAD_SELECT}")
    if lead.get("statecode") != LEAD_OPEN:
        raise ValueError(f"lead '{lead.get('subject')}' is not open (statecode {lead.get('statecode')}): "
                         "qualifying twice is not a safe no-op")
    payload = body(account, contact, opportunity, suppress_duplicates)
    what = [n for n, on in (("account", account), ("contact", contact), ("opportunity", opportunity)) if on]
    out(f"lead '{lead.get('subject')}' ({lead.get('companyname') or 'no company'}): would create {', '.join(what)}")
    if not apply:
        out("dry run: add --apply to qualify")
        return {}
    try:
        api.post(f"leads({lead_id})/Microsoft.Dynamics.CRM.QualifyLead", payload)
    except DataverseError as e:
        if e.status == 404:
            out("hint: the bound QualifyLead URL was not found; run `salesctl doctor` to read the action's "
                "binding from $metadata")
        raise
    res = api.get(f"leads({lead_id})?$select={RESULT_SELECT}")
    out(f"qualified: statecode {res.get('statecode')} statuscode {res.get('statuscode')}  "
        f"opportunity {res.get('_qualifyingopportunityid_value') or '-'}  "
        f"account {res.get('_parentaccountid_value') or '-'}  contact {res.get('_parentcontactid_value') or '-'}")
    return res
