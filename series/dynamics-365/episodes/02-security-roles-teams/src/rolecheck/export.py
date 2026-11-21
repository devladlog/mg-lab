"""Export the security model of an environment for a few tables into the JSON that model.py reads. Read-only.

Why RetrieveRolePrivilegesRole per role and not RetrieveUserPrivileges per user: Learn notes that
RetrieveUserPrivileges only returns the Basic (User) depth for privileges a user inherits through team
membership, whatever depth the team's roles really grant. Reading each role's privileges (with their depth)
and the team memberships separately avoids that trap.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from .webapi import WebApi

DEPTH_FROM_API = {"Basic": "User", "Local": "BusinessUnit", "Deep": "ParentChild", "Global": "Organization"}
TEAM_TYPE = {0: "owner", 1: "access", 2: "entra-security", 3: "entra-office"}
OWNERSHIP = {"UserOwned": "user", "TeamOwned": "user", "OrganizationOwned": "organization"}
_PRV = re.compile(r"^prv(AppendTo|Append|Assign|Create|Delete|Read|Share|Write)(.+)$")


def parse_privilege_name(name: str) -> Optional[tuple]:
    """'prvAppendTomgl_ProjectRequest' -> ('AppendTo', 'mgl_projectrequest'). Naming: prv + Verb + table SchemaName."""
    m = _PRV.match(name or "")
    return (m.group(1), m.group(2).lower()) if m else None


def export_model(api: WebApi, tables: Iterable[str], *, max_records: int = 50,
                 include_shares: bool = True, warn=print) -> Dict[str, Any]:
    tables = [t.lower() for t in tables]
    model: Dict[str, Any] = {"business_units": [], "tables": {}, "roles": [], "users": [], "teams": [],
                             "records": [], "shares": []}

    for bu in api.get_all("businessunits?$select=businessunitid,name,_parentbusinessunitid_value"):
        model["business_units"].append({"id": bu["businessunitid"], "name": bu["name"],
                                        "parent": bu.get("_parentbusinessunitid_value")})

    entity_sets = {}
    for t in tables:
        meta = api.get(f"EntityDefinitions(LogicalName='{t}')?$select=OwnershipType,EntitySetName,PrimaryIdAttribute")
        model["tables"][t] = {"ownership": OWNERSHIP.get(meta.get("OwnershipType"), "user")}
        entity_sets[t] = (meta["EntitySetName"], meta["PrimaryIdAttribute"])

    users = list(api.get_all("systemusers?$select=systemuserid,fullname,_businessunitid_value,isdisabled"
                             "&$filter=isdisabled eq false&$expand=systemuserroles_association($select=roleid)"))
    teams = list(api.get_all("teams?$select=teamid,name,teamtype,_businessunitid_value"
                             "&$expand=teamroles_association($select=roleid),"
                             "teammembership_association($select=systemuserid)"))
    role_ids = {r["roleid"] for u in users for r in u.get("systemuserroles_association", [])}
    role_ids |= {r["roleid"] for t in teams for r in t.get("teamroles_association", [])}

    privilege_names: Dict[str, str] = {}
    for rid in sorted(role_ids):
        role = api.get(f"roles({rid})?$select=roleid,name,isinherited,_businessunitid_value")
        rp = api.get(f"RetrieveRolePrivilegesRole(RoleId={rid})").get("RolePrivileges", [])
        privs: Dict[str, Dict[str, str]] = {}
        for p in rp:
            name = p.get("PrivilegeName")
            if not name:   # fall back to the privilege table if the name isn't returned
                if not privilege_names:
                    privilege_names = {x["privilegeid"]: x["name"] for x in api.get_all("privileges?$select=name")}
                name = privilege_names.get(p["PrivilegeId"], "")
            parsed = parse_privilege_name(name)
            if not parsed or parsed[1] not in tables:
                continue
            depth = DEPTH_FROM_API.get(p.get("Depth"))
            if depth is None:
                warn(f"role {role['name']}: {name} has depth {p.get('Depth')!r} (not modelled) - skipped")
                continue
            privs.setdefault(parsed[1], {})[parsed[0]] = depth
        model["roles"].append({"id": rid, "name": role["name"], "business_unit": role.get("_businessunitid_value"),
                               "inherited": role.get("isinherited", 1) == 1, "privileges": privs})

    for u in users:
        model["users"].append({"id": u["systemuserid"], "name": u["fullname"],
                               "business_unit": u["_businessunitid_value"],
                               "roles": [r["roleid"] for r in u.get("systemuserroles_association", [])]})
    user_ids = {u["systemuserid"] for u in users}
    for t in teams:
        model["teams"].append({"id": t["teamid"], "name": t["name"], "type": TEAM_TYPE.get(t.get("teamtype"), "owner"),
                               "business_unit": t["_businessunitid_value"],
                               "roles": [r["roleid"] for r in t.get("teamroles_association", [])],
                               "members": [m["systemuserid"] for m in t.get("teammembership_association", [])
                                           if m["systemuserid"] in user_ids]})

    for t, (entity_set, pk) in entity_sets.items():
        if model["tables"][t]["ownership"] != "user":
            continue
        q = f"{entity_set}?$select={pk},_ownerid_value,_owningbusinessunit_value&$top={max_records}"
        for rec in api.get(q, annotations=True).get("value", []):
            owner_type = rec.get("_ownerid_value@Microsoft.Dynamics.CRM.lookuplogicalname", "systemuser")
            model["records"].append({"table": t, "id": rec[pk],
                                     "owner": {"type": "team" if owner_type == "team" else "user",
                                               "id": rec["_ownerid_value"]},
                                     "business_unit": rec.get("_owningbusinessunit_value")})
            if include_shares:
                model["shares"] += _shares(api, entity_set, rec[pk])
    _drop_unknown_owners(model, warn)
    return model


def _shares(api: WebApi, entity_set: str, record_id: str) -> List[Dict[str, Any]]:
    res = api.get(f"RetrieveSharedPrincipalsAndAccess(Target=@p1)?@p1={{'@odata.id':'{entity_set}({record_id})'}}")
    out = []
    for pa in res.get("PrincipalAccesses", []):
        kind = pa["Principal"].get("@odata.type", "").split(".")[-1]
        rights = [r.strip().removesuffix("Access") for r in pa.get("AccessMask", "").split(",") if r.strip()]
        out.append({"record": record_id,
                    "principal": {"type": "team" if kind == "team" else "user", "id": pa["Principal"]["ownerid"]},
                    "rights": rights})
    return out


def _drop_unknown_owners(model: Dict[str, Any], warn) -> None:
    """Records owned by disabled users (not exported) would break validation: drop them with a warning."""
    known = {u["id"] for u in model["users"]} | {t["id"] for t in model["teams"]}
    keep = []
    for r in model["records"]:
        if r["owner"]["id"] in known:
            keep.append(r)
        else:
            warn(f"record {r['id']}: owner {r['owner']['id']} not exported (disabled?) - skipped")
    model["records"] = keep
    ids = {r["id"] for r in keep}
    model["shares"] = [s for s in model["shares"] if s["record"] in ids and s["principal"]["id"] in known]
