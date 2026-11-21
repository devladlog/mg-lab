"""Which Retail Prices API row prices a resource. Only always-on, fixed-price resources are mapped:
they are the part of the bill you decide at deployment time. Usage-based resources (storage, logs,
Functions on consumption, data transfer) are listed as "not estimated", never guessed.

Every mapping below was checked against real API rows (Sweden Central, EUR, Nov 2026):
  * App Service: productName says "- Linux" for Linux plans; armSkuName is empty for B1
    but filled for P1 v3, so we filter on skuName ("P1 v3", with a space) and productName
  * Private endpoint: priced under armRegionName 'Global', not the endpoint's region
  * Standard HDD disk: the tier comes from the size (S4 = 32 GiB ... S80); filter the
    "S4 LRS Disk" meter, or the "S4 LRS Disk Operations" row comes back too
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .prices import PriceQuery

APP_SERVICE_TIERS = {"B": "Basic", "S": "Standard", "P": "Premium"}

# Learn: Azure managed disk types, Standard HDD sizes (GiB)
STANDARD_HDD_TIERS = [(32, "S4"), (64, "S6"), (128, "S10"), (256, "S15"), (512, "S20"), (1024, "S30"),
                      (2048, "S40"), (4096, "S50"), (8192, "S60"), (16384, "S70"), (32767, "S80")]


@dataclass(frozen=True)
class LineItem:
    resource_id: str
    resource_type: str
    description: str
    query: PriceQuery
    quantity: float = 1


@dataclass(frozen=True)
class NotEstimated:
    resource_id: str
    resource_type: str
    reason: str


def resource_type(resource: dict) -> str:
    if resource.get("type"):
        return resource["type"]
    # /subscriptions/../providers/Microsoft.Web/serverfarms/name[/child/name]
    rid = resource.get("id", "")
    m = re.search(r"/providers/([^/]+)/(.+)$", rid)
    if not m:
        return "unknown"
    segments = m.group(2).split("/")
    return m.group(1) + "/" + "/".join(segments[0::2])


def app_service_sku(sku_name: str) -> tuple[str, str]:
    """'B1' -> ('B1', 'Basic'); 'P1v3' -> ('P1 v3', 'Premium v3'). Free/Shared aren't billed hourly."""
    m = re.fullmatch(r"([BSP])(\d)(?:v(\d))?", sku_name, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"App Service SKU '{sku_name}' isn't mapped")
    letter, size, gen = m.group(1).upper(), m.group(2), m.group(3)
    tier = APP_SERVICE_TIERS[letter] + (f" v{gen}" if gen else "")
    return (f"{letter}{size} v{gen}" if gen else f"{letter}{size}"), tier


def standard_hdd_tier(size_gb: int) -> str:
    for limit, tier in STANDARD_HDD_TIERS:
        if size_gb <= limit:
            return tier
    raise ValueError(f"disk size {size_gb} GiB is larger than S80")


def price_rules(resource: dict) -> list[LineItem] | NotEstimated:
    rid = resource.get("id", "?")
    rtype = resource_type(resource)
    t = rtype.lower()
    region = (resource.get("location") or "").lower().replace(" ", "")
    sku = resource.get("sku") or {}
    props = resource.get("properties") or {}

    if t == "microsoft.web/serverfarms":
        name = sku.get("name", "")
        if name.upper().startswith(("F", "D")):
            return NotEstimated(rid, rtype, f"App Service plan {name} (Free/Shared): no hourly charge")
        try:
            sku_name, tier = app_service_sku(name)
        except ValueError as e:
            return NotEstimated(rid, rtype, str(e))
        linux = bool(props.get("reserved")) or "linux" in (resource.get("kind") or "").lower()
        product = f"Azure App Service {tier} Plan" + (" - Linux" if linux else "")
        instances = int(sku.get("capacity") or 1)
        return [LineItem(rid, rtype, f"App Service plan {name} x{instances} ({'Linux' if linux else 'Windows'})",
                         PriceQuery("Azure App Service", region, sku_name, product), instances)]

    if t == "microsoft.network/privateendpoints":
        return [LineItem(rid, rtype, "Private endpoint (hourly; data processed not included)",
                         PriceQuery("Virtual Network", "Global", "Standard", "Virtual Network Private Link",
                                    "Standard Private Endpoint"))]

    if t == "microsoft.network/publicipaddresses":
        if (sku.get("name") or "Basic") != "Standard":
            return NotEstimated(rid, rtype, f"public IP SKU {sku.get('name')} isn't mapped")
        return [LineItem(rid, rtype, "Standard static public IPv4",
                         PriceQuery("Virtual Network", region, "Standard", "IP Addresses",
                                    "Standard IPv4 Static Public IP"))]

    if t == "microsoft.compute/disks":
        disk_sku = sku.get("name", "")
        if disk_sku != "Standard_LRS":
            return NotEstimated(rid, rtype, f"disk SKU {disk_sku} isn't mapped (only Standard_LRS)")
        tier = standard_hdd_tier(int(props.get("diskSizeGB") or 0))
        return [LineItem(rid, rtype, f"Standard HDD {tier} LRS ({props.get('diskSizeGB')} GiB, capacity only)",
                         PriceQuery("Storage", region, f"{tier} LRS", "Standard HDD Managed Disks",
                                    f"{tier} LRS Disk"))]

    if t == "microsoft.web/sites":
        return NotEstimated(rid, rtype, "billed through its App Service plan")
    return NotEstimated(rid, rtype, "usage-based or not mapped")
