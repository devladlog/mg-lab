"""The posture checks. Each check returns a Finding; `status` is pass, fail, warn or unknown (not collected)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .model import COPILOT_DLP_LOCATION_ID, Snapshot, as_bool, as_list

LEARN = {
    "audit": "https://learn.microsoft.com/purview/audit-log-enable-disable",
    "labels": "https://learn.microsoft.com/purview/ai-microsoft-purview#sensitivity-labels-and-ai-interactions",
    "dlp": "https://learn.microsoft.com/purview/dlp-microsoft365-copilot-location-learn-about",
    "eeeu": "https://learn.microsoft.com/sharepoint/data-access-governance-detailed-eeeu-everyone-permissions-report",
    "rcd": "https://learn.microsoft.com/sharepoint/restricted-content-discovery",
    "spo": "https://learn.microsoft.com/microsoft-365/copilot/get-ready-copilot-sharepoint-advanced-management",
}

# Set-SPOTenant / Set-SPOSite -SharingCapability accepted values (Learn): Disabled, ExternalUserSharingOnly,
# ExternalUserAndGuestSharing, ExistingExternalUserSharingOnly. Mapping to the admin center names (Anyone = ExternalUserAndGuestSharing,
# New and existing guests = ExternalUserSharingOnly, Existing guests = ExistingExternalUserSharingOnly) is not stated on that page: confirm on the tenant.
ANYONE = {"externaluserandguestsharing", "anyone"}
EXTERNAL = {"externalusersharingonly", "existingexternalusersharingonly"}


@dataclass
class Finding:
    id: str
    title: str
    status: str  # pass | fail | warn | unknown
    severity: str  # high | medium | low
    detail: str
    fix: str = ""
    learn: str = ""
    items: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _norm(value) -> str:
    return str(value or "").replace(" ", "").replace("_", "").lower()


def _unknown(id_: str, title: str, severity: str, snap: Snapshot, section: str) -> Finding:
    why = snap.errors.get(section, "section not present in the snapshot")
    return Finding(id_, title, "unknown", severity, f"Not collected: {why}")


def is_copilot_dlp_policy(policy: dict) -> bool:
    planes = [_norm(p) for p in as_list(policy.get("EnforcementPlanes"))]
    if "copilotexperiences" in planes:
        return True
    locations = policy.get("Locations")
    text = locations if isinstance(locations, str) else json.dumps(locations or "")
    return COPILOT_DLP_LOCATION_ID in text.lower()


def check_audit(snap: Snapshot) -> Finding:
    title = "Unified audit log ingestion is on"
    section = snap.section("auditLog")
    if section is None:
        return _unknown("G01", title, "high", snap, "auditLog")
    enabled = as_bool(section.get("UnifiedAuditLogIngestionEnabled"))
    if enabled:
        return Finding("G01", title, "pass", "high", "UnifiedAuditLogIngestionEnabled is True.", learn=LEARN["audit"])
    return Finding("G01", title, "fail", "high",
                   "Auditing is off: no Copilot interaction records, no DSPM activity data.",
                   fix="Set-AdminAuditLogConfig -UnifiedAuditLogIngestionEnabled $true", learn=LEARN["audit"])


def check_labels(snap: Snapshot) -> Finding:
    title = "Sensitivity labels exist and are published"
    labels = snap.section("labels")
    policies = snap.section("labelPolicies")
    if labels is None:
        return _unknown("G02", title, "high", snap, "labels")
    active = [x for x in labels if as_bool(x.get("Disabled")) is not True]
    if not active:
        return Finding("G02", title, "fail", "high", "No enabled sensitivity label. Without labels, Copilot has nothing "
                       "to honour and DLP cannot exclude labelled items.",
                       fix="Purview portal, Information Protection, Sensitivity labels (or the DSPM one-click default labels).",
                       learn=LEARN["labels"])
    if policies is not None and not [p for p in policies if as_bool(p.get("Enabled")) is not False]:
        return Finding("G02", title, "fail", "high", f"{len(active)} label(s) but no enabled label policy: users cannot apply them.",
                       fix="Publish the labels with a label policy.", learn=LEARN["labels"])
    return Finding("G02", title, "pass", "high", f"{len(active)} enabled label(s)"
                   + (f", {len(policies)} label policy(ies)." if policies is not None else "."), learn=LEARN["labels"])


def check_copilot_dlp(snap: Snapshot) -> list[Finding]:
    title = "A DLP policy covers the Microsoft Copilot location"
    policies = snap.section("dlpPolicies")
    if policies is None:
        return [_unknown("G03", title, "high", snap, "dlpPolicies")]
    copilot = [p for p in policies if is_copilot_dlp_policy(p)]
    if not copilot:
        return [Finding("G03", title, "fail", "high",
                        "No DLP policy targets the Microsoft Copilot, Copilot Chat, and Copilot Cowork location.",
                        fix="scripts/New-CopilotLabelDlpPolicy.ps1 (simulation first), or Purview, Data Loss Prevention, Policies, Custom.",
                        learn=LEARN["dlp"])]
    out = [Finding("G03", title, "pass", "high", "Policies: " + ", ".join(str(p.get("Name")) for p in copilot) + ".",
                   learn=LEARN["dlp"])]
    enforcing = [p for p in copilot if _norm(p.get("Mode")) in ("enable", "enforce", "") and as_bool(p.get("Enabled")) is not False]
    if enforcing:
        out.append(Finding("G04", "At least one Copilot DLP policy enforces (not simulation)", "pass", "medium",
                           f"{len(enforcing)} enforcing.", learn=LEARN["dlp"]))
    else:
        modes = ", ".join(f"{p.get('Name')}={p.get('Mode')}" for p in copilot)
        out.append(Finding("G04", "At least one Copilot DLP policy enforces (not simulation)", "warn", "medium",
                           f"All Copilot DLP policies are in simulation or disabled ({modes}). Fine for a pilot, "
                           "nothing is blocked yet. Learn: updates can take up to four hours to reach Copilot.",
                           fix="Review the simulation results, then switch the policy to Enable.", learn=LEARN["dlp"]))
    return out


def check_eeeu(snap: Snapshot) -> Finding:
    title = "Everyone-except-external-users is hard to hand out"
    tenant = snap.section("sharePointTenant")
    if tenant is None:
        return _unknown("G05", title, "medium", snap, "sharePointTenant")
    show = as_bool(tenant.get("ShowEveryoneExceptExternalUsersClaim"))
    private = as_bool(tenant.get("AllowEveryoneExceptExternalUsersClaimInPrivateSite"))
    problems = []
    if show:
        problems.append("ShowEveryoneExceptExternalUsersClaim is True (the people picker offers the group)")
    if private:
        problems.append("AllowEveryoneExceptExternalUsersClaimInPrivateSite is True (it can be added to private sites)")
    if problems:
        return Finding("G05", title, "warn", "medium", "; ".join(problems) + ". Content granted to this group is visible "
                       "to every internal user and surfaces in Copilot search.",
                       fix="Set-SPOTenant -ShowEveryoneExceptExternalUsersClaim $false (and -AllowEveryoneExceptExternalUsersClaimInPrivateSite $false); "
                           "existing grants stay until you remove them.", learn=LEARN["eeeu"])
    return Finding("G05", title, "pass", "medium", "The group is not offered in the people picker and not allowed on private sites.",
                   learn=LEARN["eeeu"])


def check_tenant_sharing(snap: Snapshot) -> Finding:
    title = "Tenant sharing is not set to Anyone links"
    tenant = snap.section("sharePointTenant")
    if tenant is None:
        return _unknown("G06", title, "medium", snap, "sharePointTenant")
    cap = _norm(tenant.get("SharingCapability"))
    if cap in ANYONE:
        return Finding("G06", title, "warn", "medium", "SharingCapability allows Anyone links (anonymous).",
                       fix="Set-SPOTenant -SharingCapability ExternalUserSharingOnly (new and existing guests) or stricter, per your sharing policy.",
                       learn=LEARN["spo"])
    return Finding("G06", title, "pass", "medium", f"SharingCapability = {tenant.get('SharingCapability')}.", learn=LEARN["spo"])


def check_sites(snap: Snapshot) -> list[Finding]:
    sites = snap.section("sites")
    if sites is None:
        return [_unknown("G07", "Sites with external sharing are labelled", "medium", snap, "sites"),
                _unknown("G08", "Sites with Restricted Content Discovery", "low", snap, "sites")]
    out: list[Finding] = []
    exposed = [s for s in sites if _norm(s.get("SharingCapability")) in ANYONE | EXTERNAL and not s.get("SensitivityLabel")]
    anyone = [s for s in exposed if _norm(s.get("SharingCapability")) in ANYONE]
    if exposed:
        out.append(Finding("G07", "Sites with external sharing are labelled", "warn", "medium",
                           f"{len(exposed)} of {len(sites)} site(s) allow external sharing and carry no sensitivity label"
                           f" ({len(anyone)} with Anyone links).",
                           fix="Label the sites (container labels) or lower SharingCapability per site.",
                           learn=LEARN["spo"], items=[str(s.get("Url")) for s in exposed]))
    else:
        out.append(Finding("G07", "Sites with external sharing are labelled", "pass", "medium",
                           f"{len(sites)} site(s) checked, none with external sharing and no label.", learn=LEARN["spo"]))
    rcd = [s for s in sites if as_bool(s.get("RestrictContentOrgWideSearch"))]
    out.append(Finding("G08", "Sites with Restricted Content Discovery", "pass" if rcd else "warn", "low",
                       f"{len(rcd)} of {len(sites)} site(s) restricted. RCD is a temporary control while permissions are reviewed; "
                       "Learn requires a Microsoft 365 Copilot licence and SharePoint Advanced Management to configure it.",
                       learn=LEARN["rcd"], items=[str(s.get("Url")) for s in rcd]))
    return out


def run_checks(snap: Snapshot) -> list[Finding]:
    findings = [check_audit(snap), check_labels(snap)]
    findings += check_copilot_dlp(snap)
    findings += [check_eeeu(snap), check_tenant_sharing(snap)]
    findings += check_sites(snap)
    return sorted(findings, key=lambda f: f.id)
