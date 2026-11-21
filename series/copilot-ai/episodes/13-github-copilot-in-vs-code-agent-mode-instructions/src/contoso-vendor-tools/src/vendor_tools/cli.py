"""Command line entry point: python -m vendor_tools.cli --within-days 120"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .renewals import load_vendors, total_cost, upcoming_renewals

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "vendors.csv"


def render(vendors, today: date, within_days: int) -> str:
    rows = upcoming_renewals(vendors, today, within_days)
    lines = [f"{'Vendor':<24}{'Renews':<12}{'EUR/year':>10}"]
    for v in rows:
        lines.append(f"{v.name:<24}{v.renewal_date.isoformat():<12}{v.annual_cost_eur:>10,}")
    lines.append(f"Total: {total_cost(rows):,} EUR")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upcoming vendor renewals")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--within-days", type=int, default=90)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    print(render(load_vendors(args.data), args.today, args.within_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
