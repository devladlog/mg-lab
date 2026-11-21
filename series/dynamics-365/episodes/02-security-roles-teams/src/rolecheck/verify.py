"""Ask Dataverse itself: RetrievePrincipalAccess for a user and a record, and compare with the model's answer."""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .access import explain
from .model import SecurityModel
from .webapi import WebApi

RECORD_PRIVILEGES = ("Read", "Write", "Delete", "Append", "AppendTo", "Assign", "Share")


def principal_access(api: WebApi, user_id: str, entity_set: str, record_id: str) -> Set[str]:
    """{'Read', 'Write', ...} from the AccessRights flags, e.g. 'ReadAccess, WriteAccess'."""
    res = api.get(f"systemusers({user_id})/Microsoft.Dynamics.CRM.RetrievePrincipalAccess(Target=@p1)"
                  f"?@p1={{'@odata.id':'{entity_set}({record_id})'}}")
    flags = [f.strip() for f in res.get("AccessRights", "").split(",") if f.strip() and f.strip() != "None"]
    return {f.removesuffix("Access") for f in flags}


def compare(model: SecurityModel, dataverse_rights: Set[str], user_id: str, record_id: str
            ) -> Tuple[List[Tuple[str, bool, bool]], bool]:
    rows = []
    for p in RECORD_PRIVILEGES:
        rows.append((p, explain(model, user_id, record_id, p).allowed, p in dataverse_rights))
    return rows, all(m == d for _, m, d in rows)


def render(rows: List[Tuple[str, bool, bool]]) -> List[str]:
    yn: Dict[bool, str] = {True: "yes", False: "no"}
    out = [f"{'privilege':<10} {'model':<6} {'dataverse':<9}"]
    for p, m, d in rows:
        out.append(f"{p:<10} {yn[m]:<6} {yn[d]:<9}{'' if m == d else '  <-- differs'}")
    return out
