"""Collect the live state of every AI resource in a resource group into one JSON-serialisable snapshot."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .arm import API, Arm, rg_path

TAG = "ai-system-id"


@dataclass
class Deployment:
    name: str
    model: str
    version: str
    sku: str
    upgrade: str                 # versionUpgradeOption
    rai_policy: str
    rai_filters: list[dict] = field(default_factory=list)   # contentFilters of that policy ([] if default)


@dataclass
class Account:
    id: str
    name: str
    kind: str
    location: str
    system_id: str               # value of the ai-system-id tag ("" = untagged)
    disable_local_auth: bool
    public_network_access: str
    audit_log_categories: list[str] = field(default_factory=list)   # enabled log categories sent to a workspace
    deployments: list[Deployment] = field(default_factory=list)
    non_compliant_policies: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    subscription_id: str
    resource_group: str
    taken_at: str
    accounts: list[Account]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> "Snapshot":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        accounts = [Account(**{**a, "deployments": [Deployment(**x) for x in a["deployments"]]})
                    for a in d["accounts"]]
        return Snapshot(d["subscription_id"], d["resource_group"], d["taken_at"], accounts)


def _workspace_categories(settings: list[dict]) -> list[str]:
    """Enabled log categories (or category groups) of diagnostic settings that send to a Log Analytics workspace."""
    cats: set[str] = set()
    for s in settings:
        props = s.get("properties", {})
        if not props.get("workspaceId"):
            continue
        for log in props.get("logs", []):
            if log.get("enabled"):
                cats.add(log.get("category") or log.get("categoryGroup") or "")
    return sorted(c for c in cats if c)


def _non_compliant(by_resource: dict[str, set[str]], account_id: str) -> list[str]:
    """Assignments non-compliant on the account or on any child (deployments are child resources)."""
    root = account_id.lower()
    names: set[str] = set()
    for rid, assignments in by_resource.items():
        if rid == root or rid.startswith(root + "/"):
            names |= assignments
    return sorted(names)


def collect(arm: Arm, subscription_id: str, resource_group: str, *, now: datetime | None = None) -> Snapshot:
    rg = rg_path(subscription_id, resource_group)
    v = API["cognitive"]
    # Policy states once for the whole resource group; keep only non-compliant ones.
    states = arm.list(f"{rg}/providers/Microsoft.PolicyInsights/policyStates/latest/queryResults",
                      API["policy_states"], method="POST",
                      params={"$filter": "complianceState eq 'NonCompliant'"})
    by_resource: dict[str, set[str]] = {}
    for s in states:
        rid = (s.get("resourceId") or "").lower()
        by_resource.setdefault(rid, set()).add(s.get("policyAssignmentName") or s.get("policyDefinitionName") or "?")

    accounts = []
    for a in arm.list(f"{rg}/providers/Microsoft.CognitiveServices/accounts", v):
        props = a.get("properties", {})
        deployments = []
        for d in arm.list(f"{a['id']}/deployments", v):
            dp = d.get("properties", {})
            model = dp.get("model", {})
            policy = dp.get("raiPolicyName", "")
            filters = []
            if policy and not policy.startswith("Microsoft."):
                filters = arm.get(f"{a['id']}/raiPolicies/{policy}", v).get("properties", {}).get("contentFilters", [])
            deployments.append(Deployment(
                name=d["name"], model=model.get("name", ""), version=str(model.get("version", "")),
                sku=(d.get("sku") or {}).get("name", ""), upgrade=dp.get("versionUpgradeOption", ""),
                rai_policy=policy, rai_filters=filters))
        diag = arm.list(f"{a['id']}/providers/Microsoft.Insights/diagnosticSettings", API["diagnostics"])
        accounts.append(Account(
            id=a["id"], name=a["name"], kind=a.get("kind", ""), location=a.get("location", ""),
            system_id=(a.get("tags") or {}).get(TAG, ""),
            disable_local_auth=props.get("disableLocalAuth") is True,
            public_network_access=props.get("publicNetworkAccess", "Enabled"),
            audit_log_categories=_workspace_categories(diag), deployments=deployments,
            non_compliant_policies=_non_compliant(by_resource, a["id"])))
    taken = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Snapshot(subscription_id, resource_group, taken, accounts)
