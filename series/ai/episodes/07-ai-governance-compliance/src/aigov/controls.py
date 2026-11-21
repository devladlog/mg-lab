"""Contoso's AI controls: each one compares what the register promises with what Azure actually runs.

Status is PASS, FAIL or N/A, always with the evidence that decided it, so a reviewer can check the check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .inventory import Account
from .register import System

RAI_GATE_MAX_AGE_DAYS = 90
# Deployment types that keep processing inside a region or the EU data zone (Learn: deployment types).
EU_SKUS = {"Standard", "ProvisionedManaged", "DataZoneStandard", "DataZoneProvisionedManaged", "DataZoneBatch"}
AUDIT_CATEGORIES = {"Audit", "audit", "allLogs"}

# control id -> (title, tiers it applies to)
CONTROLS = {
    "GOV-01": ("Listed in the AI register (ai-system-id tag)", ("low", "medium", "high")),
    "GOV-02": ("Named owner and review not overdue", ("low", "medium", "high")),
    "SEC-01": ("Keyless: local (key) auth disabled", ("low", "medium", "high")),
    "SEC-02": ("Audit logs sent to Log Analytics", ("low", "medium", "high")),
    "MOD-01": ("Only approved model + version deployed", ("low", "medium", "high")),
    "MOD-02": ("Model version pinned (no auto-upgrade)", ("low", "medium", "high")),
    "MOD-03": ("Deployment type matches data residency", ("medium", "high")),
    "RAI-01": ("Custom guardrail with prompt shields", ("medium", "high")),
    "RAI-02": ("Responsible-AI gate passed in the last 90 days", ("medium", "high")),
    "RAI-03": ("Human oversight described", ("high",)),
    "POL-01": ("No non-compliant Azure Policy states", ("low", "medium", "high")),
}


@dataclass
class Finding:
    control: str
    status: str          # PASS | FAIL | N/A
    evidence: str

    @property
    def title(self) -> str:
        return CONTROLS[self.control][0] if self.control in CONTROLS else self.control


def _f(control: str, ok: bool, evidence: str) -> Finding:
    return Finding(control, "PASS" if ok else "FAIL", evidence)


def check_account(system: System, account: Account, today: date) -> list[Finding]:
    """All controls for one registered account. Controls outside the system's tier are reported as N/A."""
    out: list[Finding] = []

    def applies(cid: str) -> bool:
        if system.tier in CONTROLS[cid][1]:
            return True
        out.append(Finding(cid, "N/A", f"not required for tier {system.tier}"))
        return False

    out.append(_f("GOV-01", True, f"tag ai-system-id={account.system_id}"))
    overdue = system.next_review < today
    out.append(_f("GOV-02", bool(system.owner) and not overdue,
                  f"owner {system.owner or '(none)'}, next review {system.next_review}"
                  + (" (OVERDUE)" if overdue else "")))
    out.append(_f("SEC-01", account.disable_local_auth, f"disableLocalAuth={account.disable_local_auth}"))
    audit = sorted(AUDIT_CATEGORIES & set(account.audit_log_categories))
    out.append(_f("SEC-02", bool(audit), "workspace log categories: " + (", ".join(account.audit_log_categories)
                                                                          or "none")))
    approved = set(system.approved_models)
    deployed = [(d.name, (d.model, d.version)) for d in account.deployments]
    rogue = [f"{n}={m}:{v}" for n, (m, v) in deployed if (m, v) not in approved]
    out.append(_f("MOD-01", not rogue, "unapproved: " + ", ".join(rogue) if rogue
                  else f"{len(deployed)} deployment(s), all approved"))
    floating = [d.name for d in account.deployments if d.upgrade != "NoAutoUpgrade"]
    out.append(_f("MOD-02", not floating, "auto-upgrade on: " + ", ".join(floating) if floating
                  else "all deployments NoAutoUpgrade"))
    if applies("MOD-03"):
        if system.data_residency == "eu":
            outside = [f"{d.name}={d.sku}" for d in account.deployments if d.sku not in EU_SKUS]
            out.append(_f("MOD-03", not outside, "outside EU data zone: " + ", ".join(outside) if outside
                          else "all deployments regional or EU data zone"))
        else:
            out.append(Finding("MOD-03", "N/A", "register: data_residency any"))
    if applies("RAI-01"):
        out.append(_guardrail(system, account))
    if applies("RAI-02"):
        gate = system.rai_gate or {}
        when = gate.get("date")
        age = (today - when).days if when else None
        ok = gate.get("verdict") == "PASS" and age is not None and 0 <= age <= RAI_GATE_MAX_AGE_DAYS
        out.append(_f("RAI-02", ok, f"last gate {gate.get('verdict', 'none')} on {when or '-'}"
                      + (f" ({age} days ago)" if age is not None else "")))
    if applies("RAI-03"):
        out.append(_f("RAI-03", bool(system.human_oversight), system.human_oversight[:80] or "not described"))
    out.append(_f("POL-01", not account.non_compliant_policies,
                  "non-compliant: " + ", ".join(account.non_compliant_policies) if account.non_compliant_policies
                  else "no non-compliant states reported"))
    return out


def _guardrail(system: System, account: Account) -> Finding:
    if not account.deployments:
        return Finding("RAI-01", "N/A", "no model deployments")
    problems = []
    for d in account.deployments:
        if d.model.startswith("text-embedding"):
            continue                               # embeddings return vectors, not text: no output to filter
        if not d.rai_policy or d.rai_policy.startswith("Microsoft."):
            problems.append(f"{d.name}: default policy {d.rai_policy or '(none)'}")
            continue
        on = {f.get("name") for f in d.rai_filters if f.get("enabled") and f.get("blocking")}
        need = {"Jailbreak"} | ({"Indirect Attack"} if system.uses_retrieval else set())
        if need - on:
            problems.append(f"{d.name}: {d.rai_policy} lacks {', '.join(sorted(need - on))}")
    return _f("RAI-01", not problems, "; ".join(problems) if problems else "custom policy with prompt shields")


def unregistered(account: Account) -> Finding:
    """An AI resource nobody registered (untagged or unknown id): shadow AI, always a FAIL."""
    why = "no ai-system-id tag" if not account.system_id else f"ai-system-id '{account.system_id}' not in register"
    return Finding("GOV-01", "FAIL", why)
