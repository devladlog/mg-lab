"""Read the resource the way an auditor would: from Azure Resource Manager, with the same Entra identity.

`audit()` is a pure function over three documents (the account, its diagnostic settings, the role assignments), so the rules
can be tested without Azure. `fetch()` gets those documents. Each rule says where it comes from: Learn, or our own policy."""
from __future__ import annotations

from dataclasses import dataclass

from .endpoints import check_resource_id
from .http import ARM_SCOPE, Api

ACCOUNT_API = "2025-06-01"
DIAG_API = "2021-05-01-preview"
ROLES_API = "2022-04-01"

ROLE_NAMES = {   # built-in role ids (Learn: built-in roles)
    "a97b65f3-24c7-4388-baec-2e87135dc908": "Cognitive Services User",
    "53ca6127-db72-4b80-b1b0-d745d6d5456d": "Foundry User",
    "c883944f-8b7b-4483-af10-35834be79c4a": "Foundry Owner",
    "7628b7b8-a8b2-4cdc-b46f-e9b35248918e": "Cognitive Services Language Reader",
    "25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68": "Cognitive Services Contributor",
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
}
DATA_PLANE_ROLES = {"Cognitive Services User", "Foundry User", "Foundry Owner", "Cognitive Services Language Reader"}
REQUIRED_LOGS = ("Audit", "RequestResponse")
REQUIRED_TAGS = ("owner", "costcenter")        # our policy, not Learn's


@dataclass
class Finding:
    id: str
    level: str              # pass | warn | fail | info
    title: str
    detail: str = ""
    source: str = "Learn"


def _p(account: dict) -> dict:
    return account.get("properties") or {}


def audit(account: dict, diag_settings: list[dict] | None, role_assignments: list[dict] | None) -> list[Finding]:
    f: list[Finding] = []
    p = _p(account)
    kind, sku = account.get("kind", "?"), (account.get("sku") or {}).get("name", "?")

    if kind == "AIServices":
        f.append(Finding("kind", "pass", "Foundry resource (kind AIServices)", f"sku {sku}: one resource for Language, Translator, Content Safety, Document Intelligence, Vision, Speech and models."))
    else:
        f.append(Finding("kind", "warn", f"Single-service kind '{kind}'", "Reaches that service only. Learn: create kind AIServices for the multi-service Foundry resource."))
    state = p.get("provisioningState", "?")
    f.append(Finding("provisioning", "pass" if state == "Succeeded" else "fail", f"Provisioning state {state}"))

    sub = p.get("customSubDomainName")
    f.append(Finding("subdomain", "pass" if sub else "fail", "Custom subdomain " + ("set" if sub else "missing"),
                     "" if sub else "Learn: Microsoft Entra authentication needs the custom subdomain; a regional endpoint does not support it."))
    local_off = p.get("disableLocalAuth") is True
    f.append(Finding("local-auth", "pass" if local_off else "fail", "Key authentication " + ("disabled" if local_off else "enabled"),
                     "" if local_off else "A key reaches every service on this resource and cannot be traced to a person. Learn: disable local authentication when the organisation uses Entra."))

    net, acl = p.get("publicNetworkAccess", "Enabled"), (p.get("networkAcls") or {}).get("defaultAction", "Allow")
    if net == "Disabled":
        f.append(Finding("network", "pass", "Public network access disabled", "Reachable through private endpoints only."))
    elif acl == "Deny":
        f.append(Finding("network", "pass", "Public endpoint limited to selected networks"))
    else:
        f.append(Finding("network", "warn", "Public endpoint open to all networks", "Learn: 'All networks' is for prototypes only."))

    ds = diag_settings
    if ds is None:
        f.append(Finding("diagnostics", "info", "Diagnostic settings not readable", "The identity lacks Microsoft.Insights/diagnosticSettings/read."))
    else:
        with_ws = [d for d in ds if _p(d).get("workspaceId")]
        enabled = {l.get("category") for d in with_ws for l in _p(d).get("logs", []) if l.get("enabled")}
        missing = [c for c in REQUIRED_LOGS if c not in enabled]
        metrics = any(m.get("enabled") for d in with_ws for m in _p(d).get("metrics", []))
        if not with_ws:
            f.append(Finding("diagnostics", "fail", "No diagnostic setting sends to Log Analytics", "Without it nobody can answer who called what, or why a call failed.", "our policy"))
        elif missing:
            f.append(Finding("diagnostics", "warn", "Log categories missing: " + ", ".join(missing), "Learn lists Audit, RequestResponse and Trace for this resource type.", "our policy"))
        else:
            f.append(Finding("diagnostics", "pass", "Audit and RequestResponse logs go to Log Analytics" + (" with metrics" if metrics else ""), "", "our policy"))

    if role_assignments is None:
        f.append(Finding("roles", "info", "Role assignments not readable", "Needs Microsoft.Authorization/roleAssignments/read (Reader or Owner)."))
    else:
        named = []
        for ra in role_assignments:
            rp = _p(ra)
            rid = (rp.get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower()
            named.append((ROLE_NAMES.get(rid, rid or "?"), rp.get("principalType", "?"), "inherited" if not (rp.get("scope") or "").lower().endswith(account.get("name", "").lower()) else "resource"))
        data = [n for n in named if n[0] in DATA_PLANE_ROLES]
        mgmt_only = [n for n in named if n[0] in ("Owner", "Contributor") and not any(d[0] in DATA_PLANE_ROLES for d in data)]
        if not data:
            lvl = "fail" if local_off else "warn"
            f.append(Finding("roles", lvl, "Nobody holds a data-plane role", "Learn: Owner and Contributor include management permissions only. Without Cognitive Services User (or Foundry User) a keyless caller gets 403."))
        else:
            f.append(Finding("roles", "pass", "Data-plane access: " + ", ".join(sorted({f"{n[0]} ({n[1]})" for n in data}))))
        if mgmt_only:
            f.append(Finding("roles-mgmt", "info", "Management roles present: " + ", ".join(sorted({n[0] for n in mgmt_only})), "These do not allow calling the services."))

    tags = {k.lower(): v for k, v in (account.get("tags") or {}).items()}
    miss = [t for t in REQUIRED_TAGS if not tags.get(t)]
    f.append(Finding("tags", "warn" if miss else "pass", "Tags " + ("missing: " + ", ".join(miss) if miss else "present"), "", "our policy"))
    return f


def fetch(api: Api, resource_id: str) -> tuple[dict, list[dict] | None, list[dict] | None]:
    rid = check_resource_id(resource_id)
    base = "https://management.azure.com" + rid
    acc = api.call("GET", f"{base}?api-version={ACCOUNT_API}", ARM_SCOPE)
    if not acc.ok:
        raise RuntimeError(f"Could not read the account (HTTP {acc.status}): {acc.error_code() or acc.error}")
    ds = api.call("GET", f"{base}/providers/Microsoft.Insights/diagnosticSettings?api-version={DIAG_API}", ARM_SCOPE)
    ra = api.call("GET", f"{base}/providers/Microsoft.Authorization/roleAssignments?api-version={ROLES_API}", ARM_SCOPE, params={"$filter": "atScope()"})
    return acc.body, (ds.body.get("value", []) if ds.ok else None), (ra.body.get("value", []) if ra.ok else None)


def render(findings: list[Finding]) -> str:
    mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    lines = [f"{mark[x.level]}  {x.title}" + (f"\n      {x.detail}" if x.detail and x.level != "pass" else "") for x in findings]
    c = {k: sum(x.level == k for x in findings) for k in mark}
    lines.append(f"{c['pass']} pass, {c['warn']} warn, {c['fail']} fail, {c['info']} info")
    return "\n".join(lines)


def exit_code(findings: list[Finding]) -> int:
    return 1 if any(x.level == "fail" for x in findings) else 0
