"""The security model as data: business units, tables, roles, users, teams, records and shares.

It can be written by hand (sample/contoso-security.json) or exported from an environment (export.py).
Access levels accept both the names in the security role editor (User, BusinessUnit, ParentChild, Organization)
and the API names (Basic, Local, Deep, Global).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Set

PRIVILEGES = ("Create", "Read", "Write", "Delete", "Append", "AppendTo", "Assign", "Share")


class Depth(IntEnum):
    NONE = 0
    USER = 1           # API: Basic
    BUSINESS_UNIT = 2  # API: Local
    PARENT_CHILD = 3   # API: Deep
    ORGANIZATION = 4   # API: Global

    @classmethod
    def parse(cls, text: str) -> "Depth":
        key = text.replace(" ", "").replace(":", "").replace("_", "").lower()
        aliases = {
            "none": cls.NONE, "user": cls.USER, "basic": cls.USER,
            "businessunit": cls.BUSINESS_UNIT, "local": cls.BUSINESS_UNIT,
            "parentchild": cls.PARENT_CHILD, "parentchildbusinessunit": cls.PARENT_CHILD,
            "parentchildbusinessunits": cls.PARENT_CHILD, "deep": cls.PARENT_CHILD,
            "organization": cls.ORGANIZATION, "global": cls.ORGANIZATION,
        }
        if key not in aliases:
            raise ValueError(f"Unknown access level {text!r}")
        return aliases[key]

    @property
    def label(self) -> str:
        return {0: "None", 1: "User", 2: "Business Unit", 3: "Parent: Child BU", 4: "Organization"}[self.value]


TEAM_TYPES = ("owner", "access", "entra-security", "entra-office")   # Team.teamtype 0, 1, 2, 3


@dataclass
class BusinessUnit:
    id: str
    name: str
    parent: Optional[str] = None


@dataclass
class Role:
    id: str
    name: str
    business_unit: str
    # Role.isinherited: True = "Direct User (Basic) access level and Team privileges" (default for new roles)
    #                   False = "Team privileges only"
    inherited: bool = True
    privileges: Dict[str, Dict[str, Depth]] = field(default_factory=dict)   # table -> privilege -> depth

    def depth(self, table: str, privilege: str) -> Depth:
        return self.privileges.get(table, {}).get(privilege, Depth.NONE)


@dataclass
class User:
    id: str
    name: str
    business_unit: str
    roles: List[str] = field(default_factory=list)
    disabled: bool = False


@dataclass
class Team:
    id: str
    name: str
    type: str
    business_unit: str
    roles: List[str] = field(default_factory=list)
    members: List[str] = field(default_factory=list)


@dataclass
class Principal:
    type: str   # "user" | "team" | "organization"
    id: str = ""


@dataclass
class Record:
    table: str
    id: str
    owner: Principal
    business_unit: str


@dataclass
class Share:
    record: str
    principal: Principal
    rights: Set[str]


@dataclass
class SecurityModel:
    business_units: Dict[str, BusinessUnit]
    tables: Dict[str, str]                    # logical name -> "user" | "organization"
    roles: Dict[str, Role]
    users: Dict[str, User]
    teams: Dict[str, Team]
    records: Dict[str, Record]
    shares: List[Share]

    # ---------- business unit tree ----------
    def is_same_or_descendant(self, bu: str, ancestor: str) -> bool:
        seen = set()
        while bu and bu not in seen:
            if bu == ancestor:
                return True
            seen.add(bu)
            bu = self.business_units[bu].parent or ""
        return False

    def bu_name(self, bu: str) -> str:
        return self.business_units[bu].name if bu in self.business_units else bu

    def teams_of(self, user_id: str) -> List[Team]:
        return [t for t in self.teams.values() if user_id in t.members]

    def principal_name(self, p: Principal) -> str:
        if p.type == "user":
            return self.users[p.id].name if p.id in self.users else p.id
        if p.type == "team":
            return self.teams[p.id].name if p.id in self.teams else p.id
        return "the organization"


class ModelError(ValueError):
    pass


def from_dict(data: dict) -> SecurityModel:
    bus = {b["id"]: BusinessUnit(b["id"], b["name"], b.get("parent")) for b in data["business_units"]}
    tables = {k: v["ownership"] for k, v in data.get("tables", {}).items()}
    roles = {}
    for r in data["roles"]:
        privs = {t: {p: Depth.parse(d) for p, d in ps.items()} for t, ps in r.get("privileges", {}).items()}
        roles[r["id"]] = Role(r["id"], r["name"], r.get("business_unit", ""), bool(r.get("inherited", True)), privs)
    users = {u["id"]: User(u["id"], u["name"], u["business_unit"], list(u.get("roles", [])), bool(u.get("disabled")))
             for u in data["users"]}
    teams = {t["id"]: Team(t["id"], t["name"], t["type"], t["business_unit"], list(t.get("roles", [])),
                           list(t.get("members", []))) for t in data.get("teams", [])}
    records = {}
    for r in data.get("records", []):
        owner = Principal(r["owner"]["type"], r["owner"]["id"])
        if owner.type == "organization":
            bu = next(b.id for b in bus.values() if not b.parent)
        else:
            bu = r.get("business_unit") or (users[owner.id].business_unit if owner.type == "user"
                                            else teams[owner.id].business_unit)
        records[r["id"]] = Record(r["table"], r["id"], owner, bu)
    shares = [Share(s["record"], Principal(s["principal"]["type"], s["principal"].get("id", "")), set(s["rights"]))
              for s in data.get("shares", [])]
    model = SecurityModel(bus, tables, roles, users, teams, records, shares)
    validate(model)
    return model


def load(path: Path) -> SecurityModel:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def validate(m: SecurityModel) -> None:
    errors = []
    for bu in m.business_units.values():
        if bu.parent and bu.parent not in m.business_units:
            errors.append(f"business unit {bu.name}: unknown parent {bu.parent}")
    roots = [b for b in m.business_units.values() if not b.parent]
    if len(roots) != 1:
        errors.append(f"expected exactly one root business unit, found {len(roots)}")
    for role in m.roles.values():
        for table, privs in role.privileges.items():
            for p, d in privs.items():
                if p not in PRIVILEGES:
                    errors.append(f"role {role.name}: unknown privilege {p}")
                if m.tables.get(table) == "organization" and d not in (Depth.NONE, Depth.ORGANIZATION):
                    errors.append(f"role {role.name}: {table} is organization-owned, so {p} can only be "
                                  f"Organization or None (got {d.label})")
    for u in m.users.values():
        errors += [f"user {u.name}: unknown role {r}" for r in u.roles if r not in m.roles]
        if u.business_unit not in m.business_units:
            errors.append(f"user {u.name}: unknown business unit {u.business_unit}")
    for t in m.teams.values():
        if t.type not in TEAM_TYPES:
            errors.append(f"team {t.name}: unknown type {t.type}")
        if t.type == "access" and t.roles:
            errors.append(f"team {t.name}: access teams don't have security roles")
        errors += [f"team {t.name}: unknown role {r}" for r in t.roles if r not in m.roles]
        errors += [f"team {t.name}: unknown member {u}" for u in t.members if u not in m.users]
    for r in m.records.values():
        if r.owner.type == "team" and m.teams.get(r.owner.id, Team("", "", "access", "")).type == "access":
            errors.append(f"record {r.id}: access teams can't own records")
        if (m.tables.get(r.table) == "organization") != (r.owner.type == "organization"):
            errors.append(f"record {r.id}: owner type must be 'organization' exactly when the table is organization-owned")
    if errors:
        raise ModelError("; ".join(errors))
