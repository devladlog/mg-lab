"""Who is asking? Read the caller from App Service authentication (Easy Auth), fail closed on anything odd.

App Service injects X-MS-CLIENT-PRINCIPAL (Base64 JSON: {"auth_typ", "claims": [{"typ", "val"}], ...}) after it
has validated the caller's token. External requests can't set that header, *as long as authentication is enabled
and required on the app* (infra/main.bicep sets requireAuthentication + Return401).
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Claim names after App Service's default claims mapping, plus the short JWT names.
GROUP_CLAIMS = {"groups", "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"}
OID_CLAIMS = {"oid", "http://schemas.microsoft.com/identity/claims/objectidentifier"}
NAME_CLAIMS = {"name", "preferred_username"}


class Unauthenticated(Exception):
    """No (valid) client principal: Easy Auth is off, misconfigured, or the request bypassed it."""


class GroupOverage(Exception):
    """The token says 'too many groups to list'. Entra emits this instead of a groups claim above
    200 groups (JWT). We refuse rather than guess: the caller's documents can't be trimmed safely."""


@dataclass(frozen=True)
class Caller:
    object_id: str
    name: str
    groups: tuple[str, ...] = field(default_factory=tuple)


def parse_client_principal(header_value: str | None) -> Caller:
    if not header_value:
        raise Unauthenticated("Missing X-MS-CLIENT-PRINCIPAL.")
    try:
        doc = json.loads(base64.b64decode(header_value, validate=True))
        claims = doc["claims"]
    except (ValueError, KeyError, TypeError, binascii.Error) as e:
        raise Unauthenticated("Malformed client principal.") from e
    if not doc.get("auth_typ"):
        raise Unauthenticated("Client principal has no authentication type.")

    by_type: dict[str, list[str]] = {}
    for c in claims:
        if isinstance(c, dict) and "typ" in c and "val" in c:
            by_type.setdefault(c["typ"], []).append(str(c["val"]))

    # Overage: no groups, but "_claim_names" lists groups (or the implicit-flow "hasgroups").
    if not any(t in by_type for t in GROUP_CLAIMS):
        names = " ".join(by_type.get("_claim_names", []))
        if "groups" in names or by_type.get("hasgroups"):
            raise GroupOverage("Group overage: group membership isn't in the token.")

    oid = next((v[0] for t, v in by_type.items() if t in OID_CLAIMS), None)
    if not oid or not GUID.match(oid):
        raise Unauthenticated("No object id claim.")
    name = next((v[0] for t, v in by_type.items() if t in NAME_CLAIMS), oid)

    groups = sorted({g.lower() for t, vals in by_type.items() if t in GROUP_CLAIMS for g in vals if GUID.match(g)})
    return Caller(object_id=oid.lower(), name=name, groups=tuple(groups))
