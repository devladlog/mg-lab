"""Tell which Copilot licences a tenant really holds, from Microsoft Graph `GET /subscribedSkus`.

Input is the JSON Graph returns (`{"value": [...]}`), a bare list, or the output of
`Get-MgSubscribedSku | ConvertTo-Json -Depth 6` (PascalCase property names): keys are
normalised to lower case before reading, so every shape works.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Service plans of the Microsoft 365 Copilot add-on SKU, from
# https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference
COPILOT_ADDON_PLANS = {
    "COPILOT_STUDIO_IN_COPILOT_FOR_M365": "fe6c28b3-d468-44ea-bbd0-a10a5167435c",
    "GRAPH_CONNECTORS_COPILOT": "82d30987-df9b-4486-b146-198b21d164c7",
    "M365_COPILOT_INTELLIGENT_SEARCH": "931e4a88-a67f-48b5-814f-16a5f1e6028d",
    "M365_COPILOT_SHAREPOINT": "0aedf20c-091d-420b-aadf-30c042609612",
    "M365_COPILOT_TEAMS": "b95945de-b3bd-46db-8437-f2beb6ea2347",
    "M365_COPILOT_APPS": "a62f8878-de10-42f3-b68f-6149a25ceb97",
    "M365_COPILOT_BUSINESS_CHAT": "3f30311c-6b1e-48a4-ab79-725b469da960",
    "M365_COPILOT_CONNECTORS": "89f1c4c8-0878-40f7-804d-869c9128ab5d",
}
ADDON_SKU_PART_NUMBERS = {"Microsoft_365_Copilot", "M365_Copilot", "Microsoft_365_Copilot_EDU", "Microsoft_Copilot_for_Sales"}
STUDIO_TRIAL_SKUS = {"CCIBOTS_PRIVPREV_VIRAL"}
STUDIO_PAID_SKUS = {"VIRTUAL_AGENT_USL", "Power_Virtual_Agents"}
# Qualifying prerequisite plans (Learn "License options for Microsoft Copilot"), part numbers from the reference table.
ELIGIBLE_BASE_SKUS = {
    "SPE_E5": "Microsoft 365 E5",
    "SPE_E3": "Microsoft 365 E3",
    "O365_BUSINESS_PREMIUM": "Microsoft 365 Business Standard",
}


def _lower_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_lower_keys(v) for v in value]
    return value


def parse_skus(payload: Any) -> list[dict]:
    """Normalise any accepted shape into a list of lower-cased SKU dicts."""
    data = _lower_keys(payload)
    if isinstance(data, dict):
        data = data.get("value", [data] if "skupartnumber" in data else [])
    if not isinstance(data, list):
        raise ValueError("expected a list of subscribedSku objects or {'value': [...]}")
    return data


def load_skus(path: str | Path) -> list[dict]:
    # utf-8-sig: Windows PowerShell 5 writes a BOM with Out-File -Encoding utf8
    with open(path, encoding="utf-8-sig") as fh:
        return parse_skus(json.load(fh))


def fetch_skus(token: str, base_url: str = GRAPH_BASE, timeout: float = 30.0) -> list[dict]:
    """GET /subscribedSkus with a bearer token (needs LicenseAssignment.Read.All)."""
    req = urllib.request.Request(
        f"{base_url}/subscribedSkus",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https Graph URL by default
        return parse_skus(json.load(resp))


def _seats(sku: dict) -> dict:
    enabled = int((sku.get("prepaidunits") or {}).get("enabled") or 0)
    consumed = int(sku.get("consumedunits") or 0)
    return {
        "skuPartNumber": sku.get("skupartnumber"),
        "capabilityStatus": sku.get("capabilitystatus"),
        "enabled": enabled,
        "consumed": consumed,
        "unassigned": max(enabled - consumed, 0),
    }


def _plan_names(sku: dict) -> set[str]:
    return {str(p.get("serviceplanname")) for p in sku.get("serviceplans") or []}


def audit(skus: list[dict]) -> dict:
    addon, studio_paid, studio_trial, base = [], [], [], []
    for sku in skus:
        part = sku.get("skupartnumber")
        plans = _plan_names(sku) & set(COPILOT_ADDON_PLANS)
        if part in ADDON_SKU_PART_NUMBERS or plans:
            item = _seats(sku)
            item["copilotServicePlans"] = sorted(plans)
            addon.append(item)
        if part in STUDIO_TRIAL_SKUS:
            studio_trial.append(_seats(sku))
        if part in STUDIO_PAID_SKUS:
            studio_paid.append(_seats(sku))
        if part in ELIGIBLE_BASE_SKUS:
            item = _seats(sku)
            item["product"] = ELIGIBLE_BASE_SKUS[part]
            base.append(item)

    usable_addon = [a for a in addon if a["capabilityStatus"] == "Enabled" and a["enabled"] > 0]
    if usable_addon:
        seats = sum(a["enabled"] for a in usable_addon)
        used = sum(a["consumed"] for a in usable_addon)
        verdict = (
            f"Microsoft 365 Copilot add-on found: {seats} enabled seat(s), {used} assigned. "
            "Licensed users get Graph-grounded Copilot; everyone else keeps Copilot Chat (Basic)."
        )
    elif addon:
        verdict = "A Copilot SKU exists but is not Enabled or has no seats: check the subscription state."
    elif base:
        names = ", ".join(sorted({b["product"] for b in base}))
        verdict = (
            f"No Microsoft 365 Copilot add-on SKU. Eligible plan(s) held: {names}. Users get "
            "Copilot Chat (Basic) at no extra cost and the add-on can be bought on top."
        )
    else:
        verdict = "No Copilot add-on and no eligible base plan recognised: check the SKU list by hand."

    return {
        "skuCount": len(skus),
        "copilotAddon": addon,
        "copilotStudioTrial": studio_trial,
        "copilotStudioPaid": studio_paid,
        "eligibleBase": base,
        "verdict": verdict,
    }


def format_report(report: dict) -> str:
    lines = [f"SKUs in tenant: {report['skuCount']}"]

    def block(title: str, items: list[dict]) -> None:
        lines.append(f"{title}: {'none' if not items else ''}".rstrip())
        for i in items:
            extra = f" ({i['product']})" if "product" in i else ""
            lines.append(
                f"  - {i['skuPartNumber']}{extra}: {i['capabilityStatus']}, "
                f"{i['enabled']} enabled, {i['consumed']} assigned, {i['unassigned']} free"
            )

    block("Microsoft 365 Copilot add-on", report["copilotAddon"])
    block("Copilot Studio (paid)", report["copilotStudioPaid"])
    block("Copilot Studio (trial)", report["copilotStudioTrial"])
    block("Eligible base plans", report["eligibleBase"])
    lines.append("")
    lines.append(f"Verdict: {report['verdict']}")
    return "\n".join(lines)
