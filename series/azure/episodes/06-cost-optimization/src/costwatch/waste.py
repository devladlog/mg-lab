"""Find money left on the table with Azure Resource Graph, then put a monthly price on it.

The queries live in ../../queries/*.kql (based on the FinOps toolkit's best-practice queries on
Microsoft Learn) and run through `az graph query` (Azure CLI with the resource-graph extension).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .prices import PriceError, RetailPrices
from .rules import NotEstimated, price_rules

QUERY_DIR = Path(__file__).resolve().parents[2] / "queries"

# file -> what the finding means
CHECKS = {
    "unattached-disks.kql": "Unattached managed disk",
    "unattached-public-ips.kql": "Public IP not attached to anything",
    "empty-app-service-plans.kql": "App Service plan with no apps",
    "stopped-not-deallocated-vms.kql": "VM stopped but not deallocated (compute still billed)",
}


class AzError(RuntimeError):
    pass


def run_graph_query(query: str, az: str = "az", subscriptions: list[str] | None = None) -> list[dict]:
    """All pages of one Resource Graph query (1,000 rows per page, skip token for the rest)."""
    rows: list[dict] = []
    skip_token = None
    while True:
        cmd = [az, "graph", "query", "-q", query, "--first", "1000", "--output", "json", "--only-show-errors"]
        if subscriptions:
            cmd += ["--subscriptions", *subscriptions]
        if skip_token:
            cmd += ["--skip-token", skip_token]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise AzError(f"az graph query failed ({p.returncode}): {p.stderr.strip()[:300]}")
        page = json.loads(p.stdout)
        rows.extend(page.get("data", []))
        skip_token = page.get("skip_token") or page.get("skipToken") or page.get("$skipToken")
        if not skip_token:
            return rows


def never_used_empty_disk(row: dict) -> bool:
    """createOption Empty and no ownership change yet (LastOwnershipUpdateTime is blank until the
    disk is first attached)."""
    return row.get("createOption") == "Empty" and not row.get("lastOwnershipUpdate")


def row_to_resource(row: dict) -> dict:
    """Shape a query row like an ARM resource so the same price rules apply."""
    props = {}
    if row.get("diskSizeGB") is not None:
        props["diskSizeGB"] = row["diskSizeGB"]
    if row.get("reserved") is not None:
        props["reserved"] = row["reserved"]
    return {"id": row.get("id"), "type": row.get("type"), "location": row.get("location"),
            "sku": row.get("sku") or {}, "kind": row.get("kind"), "properties": props}


@dataclass
class Finding:
    check: str
    resource_id: str
    resource_group: str
    monthly: float | None
    note: str = ""


@dataclass
class WasteReport:
    currency: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def monthly_total(self) -> float:
        return round(sum(f.monthly or 0 for f in self.findings), 2)


def find_waste(prices: RetailPrices, az: str = "az", subscriptions: list[str] | None = None,
               query_dir: Path = QUERY_DIR) -> WasteReport:
    report = WasteReport(prices.currency)
    for file, check in CHECKS.items():
        for row in run_graph_query((query_dir / file).read_text(), az, subscriptions):
            rule = price_rules(row_to_resource(row))
            monthly, note = None, ""
            if isinstance(rule, NotEstimated):
                note = rule.reason
            else:
                try:
                    monthly = round(sum(prices.price(i.query).monthly(i.quantity) for i in rule), 2)
                except PriceError as e:
                    note = str(e)
            if file == "unattached-disks.kql" and never_used_empty_disk(row):
                # Learn: an empty managed disk has no storage allocated (and no charge) until first use
                monthly, note = 0.0, "empty and never attached: not billed until first use"
            report.findings.append(Finding(check, row.get("id", "?"), row.get("resourceGroup", "?"), monthly, note))
    return report


def to_markdown(report: WasteReport) -> str:
    c = report.currency
    lines = ["| Finding | Resource | Group | Monthly |", "|---|---|---|---|"]
    for f in sorted(report.findings, key=lambda f: -(f.monthly or 0)):
        money = f"{f.monthly:.2f} {c}" if f.monthly is not None else f"not priced ({f.note})"
        lines.append(f"| {f.check} | {f.resource_id.rsplit('/', 1)[-1]} | {f.resource_group} | {money} |")
    lines.append(f"| **Left on the table** | | | **{report.monthly_total:.2f} {c} / month** |")
    return "\n".join(lines)
