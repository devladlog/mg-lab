"""Price a deployment before it happens, from the what-if result.

`az deployment group what-if --no-pretty-print --output json` already has every expression
resolved (SKU per environment, instance count, region), which the compiled template doesn't.
Resources that will exist after the deployment (Create, Modify, NoChange, Ignore) are priced;
Delete isn't. Accepts the CLI shape (changes at the top) and the REST shape (properties.changes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .prices import PriceError, RetailPrices
from .rules import LineItem, NotEstimated, price_rules, resource_type

KEEPS_EXISTING = {"Create", "Modify", "NoChange", "Ignore", "Deploy"}


@dataclass
class PricedLine:
    item: LineItem
    monthly: float
    unit_price: float
    unit: str


@dataclass
class Estimate:
    currency: str
    priced: list[PricedLine] = field(default_factory=list)
    not_estimated: list[NotEstimated] = field(default_factory=list)

    @property
    def monthly_total(self) -> float:
        return round(sum(p.monthly for p in self.priced), 2)


def resources_from_whatif(doc: dict) -> list[dict]:
    changes = doc.get("changes")
    if changes is None:
        changes = (doc.get("properties") or {}).get("changes", [])
    if doc.get("status") not in (None, "Succeeded"):
        raise ValueError(f"what-if status is {doc.get('status')}, nothing to price")
    resources = []
    for c in changes:
        if c.get("changeType") not in KEEPS_EXISTING:
            continue
        state = c.get("after") or c.get("before")
        if not state:
            continue
        resource = dict(state)
        resource.setdefault("id", c.get("resourceId"))
        resources.append(resource)
    return resources


def estimate(resources: list[dict], prices: RetailPrices) -> Estimate:
    result = Estimate(prices.currency)
    for resource in resources:
        rule = price_rules(resource)
        if isinstance(rule, NotEstimated):
            result.not_estimated.append(rule)
            continue
        for item in rule:
            price = prices.price(item.query)       # PriceError if 0 or >1 rows: never guess
            result.priced.append(PricedLine(item, round(price.monthly(item.quantity), 2), price.unit_price, price.unit))
    return result


def to_markdown(est: Estimate, budget: float | None = None) -> str:
    c = est.currency
    lines = ["| Resource | What | Unit price | Monthly |", "|---|---|---|---|"]
    for p in sorted(est.priced, key=lambda p: -p.monthly):
        name = p.item.resource_id.rsplit("/", 1)[-1]
        lines.append(f"| {name} | {p.item.description} | {p.unit_price:.4f} {c} / {p.unit} | {p.monthly:.2f} {c} |")
    lines.append(f"| **Fixed monthly estimate** | | | **{est.monthly_total:.2f} {c}** |")
    if budget is not None:
        verdict = "within" if est.monthly_total <= budget else "OVER"
        lines.append(f"\nBudget {budget:.2f} {c}: **{verdict}**")
    by_reason: dict[str, int] = {}
    for n in est.not_estimated:
        by_reason[n.reason] = by_reason.get(n.reason, 0) + 1
    if by_reason:
        lines.append("\nNot estimated (usage-based or unmapped): " +
                     ", ".join(f"{count} x {reason}" for reason, count in sorted(by_reason.items())))
    lines.append("\nRetail list prices, 730 hours a month; your agreement's rates and usage charges differ.")
    return "\n".join(lines)


__all__ = ["Estimate", "PricedLine", "PriceError", "estimate", "resources_from_whatif", "to_markdown", "resource_type"]
