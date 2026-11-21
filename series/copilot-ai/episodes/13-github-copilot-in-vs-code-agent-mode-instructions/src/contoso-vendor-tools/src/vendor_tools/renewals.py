"""Load vendors and report upcoming renewals."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Vendor:
    name: str
    owner: str
    annual_cost_eur: int
    renewal_date: date
    notice_days: int


def load_vendors(path: Path) -> list[Vendor]:
    """Read the vendor CSV. Dates are ISO 8601 (YYYY-MM-DD)."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            Vendor(
                name=row["name"],
                owner=row["owner"],
                annual_cost_eur=int(row["annual_cost_eur"]),
                renewal_date=date.fromisoformat(row["renewal_date"]),
                notice_days=int(row["notice_days"]),
            )
            for row in csv.DictReader(handle)
        ]


def upcoming_renewals(vendors: list[Vendor], today: date, within_days: int) -> list[Vendor]:
    """Vendors renewing between today and today + within_days (inclusive), soonest first."""
    selected = [v for v in vendors if 0 <= (v.renewal_date - today).days <= within_days]
    return sorted(selected, key=lambda v: v.renewal_date)


def total_cost(vendors: list[Vendor]) -> int:
    return sum(v.annual_cost_eur for v in vendors)
