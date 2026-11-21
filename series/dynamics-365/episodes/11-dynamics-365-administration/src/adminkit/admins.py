"""Who holds the System Administrator role?

Learn (Dataverse access controls): follow minimum required access, minimize the number of users with System
Administrator. Role assignments live in the many-to-many relationships systemuserroles_association (users) and
teamroles_association (teams) on the role table; Microsoft's own application users also hold the role (Learn, System and
application users), so those are counted apart from people.
accessmode (Learn, User table): 0 Read-Write, 1 Administrative, 2 Read, 3 Support User, 4 Non-interactive, 5 Delegated Admin.
Not seen by this tool: privileges a user gets through other roles, or members of a team that holds the role.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .findings import Finding
from .webapi import WebApi, odata_string

USER_SELECT = "systemuserid,fullname,internalemailaddress,isdisabled,accessmode,applicationid"
NON_HUMAN_ACCESS = (3, 4)  # Support User, Non-interactive


def query(role_name: str) -> str:
    return (f"roles?$select=name,roleid&$filter=name eq {odata_string(role_name)}"
            f"&$expand=systemuserroles_association($select={USER_SELECT}),"
            "teamroles_association($select=teamid,name,teamtype)")


def fetch(api: WebApi, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(api.get_all(query(cfg["role_name"])))


@dataclass(frozen=True)
class Holder:
    id: str
    name: str
    email: str
    disabled: bool
    kind: str  # person | application


def holders(roles: List[Dict[str, Any]]):
    """(users, teams) holding the role in any business unit, one entry per user or team."""
    users: Dict[str, Holder] = {}
    teams: Dict[str, str] = {}
    for r in roles:
        for u in r.get("systemuserroles_association") or []:
            app = bool(u.get("applicationid")) or u.get("accessmode") in NON_HUMAN_ACCESS
            users[u["systemuserid"]] = Holder(u["systemuserid"], u.get("fullname") or "(no name)",
                                              u.get("internalemailaddress") or "", bool(u.get("isdisabled")),
                                              "application" if app else "person")
        for t in r.get("teamroles_association") or []:
            teams[t["teamid"]] = t.get("name") or "(no name)"
    return list(users.values()), teams


def analyse(roles: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Finding]:
    users, teams = holders(roles)
    role = cfg["role_name"]
    limit = cfg["admins"]["max_human_admins"]
    people = [u for u in users if u.kind == "person" and not u.disabled]
    out: List[Finding] = []
    if len(people) > limit:
        out.append(Finding("error", "A001", role, f"{len(people)} enabled people hold the role, team maximum is {limit}: "
                           + ", ".join(sorted(u.name for u in people))))
    for u in users:
        if u.kind == "person" and u.disabled:
            out.append(Finding("warning", "A002", u.name, f"disabled user still holds {role}"))
    for name in sorted(teams.values()):
        out.append(Finding("warning", "A003", name, f"team holds {role}: every member inherits it "
                           "(if the role's member privilege inheritance allows)"))
    apps = sorted(u.name for u in users if u.kind == "application" and not u.disabled)
    if apps:
        out.append(Finding("info", "A004", role, f"{len(apps)} application/non-interactive user(s) hold the role: "
                           + ", ".join(apps)))
    return out


def table(roles: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[str]:
    users, teams = holders(roles)
    lines = [f"{cfg['role_name']}: {len(users)} user(s), {len(teams)} team(s)", "",
             f"{'kind':12} {'status':9} name"]
    for u in sorted(users, key=lambda x: (x.kind, x.name)):
        lines.append(f"{u.kind:12} {'disabled' if u.disabled else 'enabled':9} {u.name}")
    for t in sorted(teams.values()):
        lines.append(f"{'team':12} {'-':9} {t}")
    return lines
