"""Least-privilege review of a security model. Each finding says what, who, and why it matters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .access import grants_for
from .model import Depth, SecurityModel

ADMIN_ROLES = {"System Administrator", "System Customizer"}
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}


@dataclass
class Finding:
    severity: str
    check: str
    subject: str
    detail: str


def audit(m: SecurityModel) -> List[Finding]:
    f: List[Finding] = []
    assigned = {r for u in m.users.values() for r in u.roles} | {r for t in m.teams.values() for r in t.roles}

    for role in m.roles.values():
        if role.name in ADMIN_ROLES:
            continue
        for table, privs in role.privileges.items():
            if m.tables.get(table) != "user":
                continue
            for p in ("Delete", "Assign", "Share"):
                if privs.get(p) == Depth.ORGANIZATION:
                    holders = _holders(m, role.id)
                    f.append(Finding("High" if p == "Delete" else "Medium", "org-wide-destructive",
                                     f"role '{role.name}'",
                                     f"{p} at Organization level on {table} (held by {holders or 'nobody yet'}). "
                                     "Prefer Business Unit or Parent: Child, or a time-boxed assignment."))
        if role.id not in assigned:
            f.append(Finding("Low", "unused-role", f"role '{role.name}'", "not assigned to any user or team"))
        if not role.inherited and any(t for t in m.teams.values() if role.id in t.roles and t.type != "owner"
                                      and t.type != "access"):
            f.append(Finding("Info", "team-only-on-group-team", f"role '{role.name}'",
                             "'Team privileges only' on a Microsoft Entra group team: members can only use its "
                             "User-level privileges on records the team owns."))

    for u in m.users.values():
        if u.disabled:
            continue
        teams = m.teams_of(u.id)
        if not u.roles and not any(t.roles for t in teams):
            where = ", ".join(t.name for t in teams) or "no teams"
            f.append(Finding("Medium", "no-privileges", f"user '{u.name}'",
                             f"no security role directly or through a team ({where}). Records shared with them "
                             "still fail the privilege check."))
        if not u.roles and teams and all(not m.roles[r].inherited for t in teams for r in t.roles) \
                and any(t.roles for t in teams):
            f.append(Finding("Info", "team-only-user", f"user '{u.name}'",
                             "every role comes from teams with 'Team privileges only': can create and use "
                             "User-level records only with a team as owner."))

    for rec in m.records.values():
        if rec.owner.type != "team":
            continue
        team = m.teams[rec.owner.id]
        if not any(grants_for(m, m.users[uid], rec.table, "Read") for uid in team.members):
            f.append(Finding("Medium", "unreadable-team-records", f"team '{team.name}'",
                             f"owns {rec.id} but no member can pass the Read privilege check on {rec.table}"))

    return sorted(f, key=lambda x: (SEVERITY_ORDER[x.severity], x.check, x.subject))


def _holders(m: SecurityModel, role_id: str) -> str:
    names = [u.name for u in m.users.values() if role_id in u.roles]
    names += [f"team {t.name}" for t in m.teams.values() if role_id in t.roles]
    return ", ".join(names)
