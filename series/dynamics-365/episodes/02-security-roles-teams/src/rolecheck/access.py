"""Why can (or can't) this user do this to this record? The documented algorithm, step by step.

Follows "How access to a record is determined" (Power Platform admin docs):

1. Privilege check: the user needs the privilege for the table from a role assigned directly or to a team they
   belong to. The access level is NOT considered here.
2. Access check: any one of
   - Ownership: the user owns the record, or belongs to the team that owns it (any access level suffices);
   - Role access: the access level of a role covers the record's business unit
     (Business Unit = same BU, Parent: Child = same BU or below, Organization = anywhere). For a team's role the
     reference business unit is the team's;
   - Shared access: the record is shared with the user, a team they belong to, or the organization;
   - Hierarchy access (manager/position hierarchy security) - not modelled here.
   Exception: a team role with User (Basic) access whose "Member's privilege inheritance" is
   "Team privileges only" can only be used on records owned by that team.

Not modelled (say so when you use this): hierarchy security, access inherited through related records (cascading
shares), modernized business units (roles from other BUs), column-level security, filtered record ownership.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .model import Depth, Record, SecurityModel, User


@dataclass
class Grant:
    """One place the privilege comes from."""
    role: str
    depth: Depth
    via_team: Optional[str]       # team id, or None for a direct role
    anchor_bu: str                # business unit that Business Unit / Parent: Child levels are measured from
    team_only: bool = False       # User-level team role with "Team privileges only"

    def describe(self, m: SecurityModel) -> str:
        src = f"role '{m.roles[self.role].name}'"
        if self.via_team:
            src += f" via team '{m.teams[self.via_team].name}'"
            if self.team_only:
                src += " (Team privileges only)"
        return f"{src} at {self.depth.label} level"


@dataclass
class Decision:
    allowed: bool
    privilege: str
    privilege_check: bool
    grants: List[Grant] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)       # every way access is granted (there can be several)
    reasons: List[str] = field(default_factory=list)     # why each grant didn't apply, when denied

    def lines(self) -> List[str]:
        head = "ALLOWED" if self.allowed else "DENIED"
        out = [f"{head}: {self.privilege}"]
        out.append(f"  privilege check: {'passed' if self.privilege_check else 'FAILED - no role grants it'}")
        out += [f"  + {p}" for p in self.paths]
        out += [f"  - {r}" for r in self.reasons]
        return out


def grants_for(m: SecurityModel, user: User, table: str, privilege: str) -> List[Grant]:
    grants: List[Grant] = []
    for rid in user.roles:
        d = m.roles[rid].depth(table, privilege)
        if d > Depth.NONE:
            grants.append(Grant(rid, d, None, user.business_unit))
    for team in m.teams_of(user.id):
        for rid in team.roles:                     # access teams have no roles, so they add nothing here
            role = m.roles[rid]
            d = role.depth(table, privilege)
            if d > Depth.NONE:
                grants.append(Grant(rid, d, team.id, team.business_unit,
                                    team_only=(d == Depth.USER and not role.inherited)))
    return grants


def explain(m: SecurityModel, user_id: str, record_id: str, privilege: str) -> Decision:
    user, record = m.users[user_id], m.records[record_id]
    grants = grants_for(m, user, record.table, privilege)
    d = Decision(False, privilege, bool(grants), grants)
    if user.disabled:
        d.privilege_check = False
        d.reasons.append(f"{user.name} is disabled")
        return d
    if not grants:
        teams = m.teams_of(user.id)
        if teams and all(t.type == "access" or not t.roles for t in teams) and not user.roles:
            d.reasons.append("member only of teams without roles: teams that don't have roles give no privileges")
        d.reasons.append(f"no role, direct or through a team, grants {privilege} on {record.table}")
        return d

    if m.tables.get(record.table) == "organization":
        # Organization-owned: the level is Organization or None, so passing the privilege check is enough.
        d.paths += [f"organization-owned table: {g.describe(m)}" for g in grants]
        d.allowed = True
        return d

    _ownership(m, user, record, grants, d)
    _role_access(m, record, grants, d)
    _shared(m, user, record, privilege, d)
    d.allowed = bool(d.paths)
    if d.allowed:
        d.reasons.clear()
    return d


def _ownership(m: SecurityModel, user: User, record: Record, grants: List[Grant], d: Decision) -> None:
    owner = record.owner
    my_team_ids = {t.id for t in m.teams_of(user.id)}
    owns = owner.type == "user" and owner.id == user.id
    team_owns = owner.type == "team" and owner.id in my_team_ids
    if not (owns or team_owns):
        return
    for g in grants:
        if g.team_only and not (owner.type == "team" and owner.id == g.via_team):
            d.reasons.append(f"{g.describe(m)}: only usable on records owned by that team")
            continue
        who = "owns the record" if owns else f"is a member of owner team '{m.teams[owner.id].name}'"
        d.paths.append(f"ownership: user {who}; {g.describe(m)}")


def _role_access(m: SecurityModel, record: Record, grants: List[Grant], d: Decision) -> None:
    rec_bu = m.bu_name(record.business_unit)
    for g in grants:
        anchor = m.bu_name(g.anchor_bu)
        if g.depth == Depth.ORGANIZATION:
            d.paths.append(f"role access: {g.describe(m)} covers every business unit")
        elif g.depth == Depth.PARENT_CHILD and m.is_same_or_descendant(record.business_unit, g.anchor_bu):
            d.paths.append(f"role access: {g.describe(m)}; record's BU '{rec_bu}' is '{anchor}' or below it")
        elif g.depth == Depth.BUSINESS_UNIT and record.business_unit == g.anchor_bu:
            d.paths.append(f"role access: {g.describe(m)}; record is in '{anchor}'")
        elif g.depth == Depth.USER:
            if not g.team_only:
                d.reasons.append(f"{g.describe(m)}: User level only covers records the user (or their team) owns "
                                 "or that are shared with them")
            elif record.owner.id != g.via_team:
                d.reasons.append(f"{g.describe(m)}: only usable on records owned by that team")
        else:
            scope = "only" if g.depth == Depth.BUSINESS_UNIT else "and below"
            d.reasons.append(f"{g.describe(m)}: covers '{anchor}' {scope}, record is in '{rec_bu}'")


def _shared(m: SecurityModel, user: User, record: Record, privilege: str, d: Decision) -> None:
    my_team_ids = {t.id for t in m.teams_of(user.id)}
    for s in m.shares:
        if s.record != record.id:
            continue
        p = s.principal
        hit = (p.type == "user" and p.id == user.id) or (p.type == "team" and p.id in my_team_ids) \
            or p.type == "organization"
        if not hit:
            continue
        if privilege in s.rights:
            d.paths.append(f"shared access: record shared with {m.principal_name(p)} ({', '.join(sorted(s.rights))})")
        else:
            d.reasons.append(f"shared with {m.principal_name(p)}, but only for {', '.join(sorted(s.rights))}")


def who_has_access(m: SecurityModel, record_id: str, privilege: str) -> List[tuple]:
    """Like 'Check access' -> who has access: every enabled user that can, with their first path."""
    out = []
    for u in sorted(m.users.values(), key=lambda x: x.name):
        dec = explain(m, u.id, record_id, privilege)
        if dec.allowed:
            out.append((u.name, dec.paths[0]))
    return out
