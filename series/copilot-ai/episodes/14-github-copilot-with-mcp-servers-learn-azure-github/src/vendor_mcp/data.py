"""Pure logic, no MCP imports: easy to test and reuse."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent / "data" / "vendors.json"


class VendorError(ValueError):
    """Raised for input the caller can fix (unknown vendor, bad date)."""


def load(path: Path | None = None) -> list[dict]:
    with (path or DEFAULT_FILE).open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_today(today: str | None) -> date:
    if today is None:
        return date.today()
    try:
        return date.fromisoformat(today)
    except ValueError as exc:
        raise VendorError(f"today must be YYYY-MM-DD, got '{today}'") from exc


def notice_deadline(vendor: dict) -> date:
    return date.fromisoformat(vendor["renewal_date"]) - timedelta(days=int(vendor["notice_days"]))


def describe(vendor: dict, today: date) -> dict:
    renewal = date.fromisoformat(vendor["renewal_date"])
    deadline = notice_deadline(vendor)
    return {
        "name": vendor["name"],
        "service": vendor["service"],
        "owner": vendor["owner"],
        "annual_cost_eur": vendor["annual_cost_eur"],
        "renewal_date": renewal.isoformat(),
        "days_to_renewal": (renewal - today).days,
        "notice_deadline": deadline.isoformat(),
        "notice_deadline_passed": deadline < today,
    }


def list_renewals(vendors: list[dict], within_days: int, today: date) -> list[dict]:
    if within_days < 0:
        raise VendorError("within_days must be 0 or more")
    rows = [describe(v, today) for v in vendors]
    rows = [r for r in rows if 0 <= r["days_to_renewal"] <= within_days]
    return sorted(rows, key=lambda r: r["renewal_date"])


def find_vendor(vendors: list[dict], name: str, today: date) -> dict:
    wanted = name.strip().lower()
    hits = [v for v in vendors if wanted and wanted in v["name"].lower()]
    if not hits:
        raise VendorError(f"no vendor matches '{name}'; known: {', '.join(v['name'] for v in vendors)}")
    if len(hits) > 1:
        raise VendorError(f"'{name}' matches several vendors: {', '.join(v['name'] for v in hits)}")
    return describe(hits[0], today)
