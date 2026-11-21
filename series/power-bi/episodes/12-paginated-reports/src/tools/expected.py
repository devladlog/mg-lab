#!/usr/bin/env python3
"""What the report must show, computed straight from the CSVs (no DAX, no service): one row per store and month of a year.

Same definitions as the semantic model of episode 1: Sales Amount = sum(Quantity x Unit Price), Margin % = (amount - cost) / amount.
"""
import calendar
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent / "data" / "star"


def statement_rows(year: int):
    stores = {r["StoreKey"]: r["Store"] for r in csv.DictReader((STAR / "dim_store.csv").open(encoding="utf-8"))}
    acc = defaultdict(lambda: [Decimal(0), 0, Decimal(0)])      # amount, units, cost
    for r in csv.DictReader((STAR / "fact_sales.csv").open(encoding="utf-8")):
        if not r["OrderDate"].startswith(f"{year}-"):
            continue
        q = int(r["Quantity"])
        a = acc[(stores[r["StoreKey"]], int(r["OrderDate"][5:7]))]
        a[0] += q * Decimal(r["UnitPrice"])
        a[1] += q
        a[2] += q * Decimal(r["UnitCost"])
    rows = []
    for (store, month), (amount, units, cost) in sorted(acc.items()):
        rows.append({"store": store, "month_number": month, "month": calendar.month_abbr[month],
                     "sales_amount": f"{amount:,.2f}", "units": f"{units:,}",
                     "margin_pct": f"{(amount - cost) / amount * 100:.1f}%"})
    return rows


if __name__ == "__main__":
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    rows = statement_rows(year)
    print(f"{year}: {len(rows)} store-month rows, {len({r['store'] for r in rows})} stores")
    for r in rows[:3]:
        print(r)
