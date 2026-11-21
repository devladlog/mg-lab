"""Open pipeline report and hygiene rules over the Opportunity table.

Columns (Opportunity table reference): estimatedvalue (Money), estimatedclosedate (DateOnly), closeprobability
(0-100), msdyn_forecastcategory (100000001 Pipeline .. 100000006 Lost), statecode (0 Open, 1 Won, 2 Lost).
Weighted value = estimatedvalue x closeprobability / 100: the arithmetic of the classic pipeline view, NOT the
forecast feature of Sales Premium.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .webapi import WebApi

SELECT = ("opportunityid,name,estimatedvalue,estimatedclosedate,closeprobability,msdyn_forecastcategory,"
          "modifiedon,_customerid_value")
FORECAST = {100000001: "Pipeline", 100000002: "Best case", 100000003: "Committed",
            100000004: "Omitted", 100000005: "Won", 100000006: "Lost"}
FMT = "@OData.Community.Display.V1.FormattedValue"


@dataclass
class Deal:
    id: str
    name: str
    customer: str
    value: float
    close: Optional[dt.date]
    probability: Optional[int]
    category: int
    modified: Optional[dt.date]

    @property
    def weighted(self) -> float:
        return self.value * (self.probability or 0) / 100

    @property
    def category_label(self) -> str:
        return FORECAST.get(self.category, str(self.category))


def _date(s: Optional[str]) -> Optional[dt.date]:
    return dt.date.fromisoformat(s[:10]) if s else None


def to_deal(row: Dict[str, Any]) -> Deal:
    return Deal(
        id=row.get("opportunityid", ""), name=row.get("name") or "(no topic)",
        customer=row.get("_customerid_value" + FMT) or "(no customer)",
        value=float(row.get("estimatedvalue") or 0), close=_date(row.get("estimatedclosedate")),
        probability=row.get("closeprobability"), category=int(row.get("msdyn_forecastcategory") or 100000001),
        modified=_date(row.get("modifiedon")))


def query(owner_id: Optional[str] = None) -> str:
    flt = "statecode eq 0" + (f" and _ownerid_value eq {owner_id}" if owner_id else "")
    return f"opportunities?$select={SELECT}&$filter={flt}&$orderby=estimatedclosedate asc"


def fetch_open(api: WebApi, owner_id: Optional[str] = None) -> List[Deal]:
    return [to_deal(r) for r in api.get_all(query(owner_id), annotations=True)]


def summarize(deals: Iterable[Deal]) -> Dict[str, Any]:
    deals = list(deals)
    by_month: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    by_cat: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for d in deals:
        for bucket, key in ((by_month, d.close.strftime("%Y-%m") if d.close else "no date"),
                            (by_cat, d.category_label)):
            b = bucket[key]
            b[0] += 1
            b[1] += d.value
            b[2] += d.weighted
    return {"count": len(deals), "value": sum(d.value for d in deals), "weighted": sum(d.weighted for d in deals),
            "by_month": dict(sorted(by_month.items())), "by_category": dict(by_cat)}


@dataclass
class Finding:
    level: str
    code: str
    deal: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():<7} {self.code}  {self.deal}: {self.message}"


def hygiene(deals: Iterable[Deal], today: dt.date, *, stale_days: int = 30, large_deal: float = 50000,
            soon_days: int = 30) -> List[Finding]:
    out: List[Finding] = []
    for d in deals:
        if d.close is None:
            out.append(Finding("error", "H002", d.name, "no estimated close date: it falls out of every forecast"))
        elif d.close < today:
            out.append(Finding("error", "H001", d.name,
                               f"estimated close date {d.close} is {(today - d.close).days} day(s) in the past"))
        if d.value <= 0:
            out.append(Finding("error", "H003", d.name, "no estimated revenue: it counts for nothing in the pipeline"))
        if d.probability is None:
            out.append(Finding("warning", "H004", d.name, "no probability: weighted value counts it as 0"))
        if d.modified and (today - d.modified).days > stale_days:
            out.append(Finding("warning", "H005", d.name, f"not touched for {(today - d.modified).days} days"))
        if (d.value >= large_deal and d.close and today <= d.close <= today + dt.timedelta(days=soon_days)
                and d.category == 100000001):
            out.append(Finding("warning", "H006", d.name,
                               f"{d.value:,.0f} closing {d.close} but the forecast category is still Pipeline"))
    return sorted(out, key=lambda f: (f.level != "error", f.code, f.deal))


def report(deals: List[Deal], today: dt.date, currency: str = "EUR") -> List[str]:
    s = summarize(deals)
    lines = [f"Open pipeline: {s['count']} opportunities, {s['value']:,.0f} {currency}, "
             f"weighted {s['weighted']:,.0f} {currency}", "", f"{'close month':<12} {'deals':>5} {'value':>10} {'weighted':>10}"]
    for k, (n, v, w) in s["by_month"].items():
        lines.append(f"{k:<12} {n:>5} {v:>10,.0f} {w:>10,.0f}")
    lines += ["", f"{'category':<12} {'deals':>5} {'value':>10} {'weighted':>10}"]
    for k, (n, v, w) in sorted(s["by_category"].items(), key=lambda kv: -kv[1][2]):
        lines.append(f"{k:<12} {n:>5} {v:>10,.0f} {w:>10,.0f}")
    return lines
