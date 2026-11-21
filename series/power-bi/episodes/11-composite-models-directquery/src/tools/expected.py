#!/usr/bin/env python3
"""Reference numbers computed straight from the CSVs (no SQL): what the SQL scripts and the DAX queries must return."""
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent / "data" / "star"


def facts():
    return list(csv.DictReader((STAR / "fact_sales.csv").open(encoding="utf-8")))


def totals(rows=None):
    rows = facts() if rows is None else rows
    amount = sum(Decimal(r["Quantity"]) * Decimal(r["UnitPrice"]) for r in rows)
    units = sum(int(r["Quantity"]) for r in rows)
    agg_rows = len({(r["OrderDate"], r["ProductKey"], r["StoreKey"]) for r in rows})
    return {"lines": len(rows), "amount": amount, "units": units, "agg_rows": agg_rows}


def by_year():
    out = defaultdict(Decimal)
    for r in facts():
        out[r["OrderDate"][:4]] += Decimal(r["Quantity"]) * Decimal(r["UnitPrice"])
    return dict(out)


if __name__ == "__main__":
    t = totals()
    print(f"as loaded: {t['lines']:,} lines, Sales Amount {t['amount']:,.2f}, Units {t['units']:,}, aggregation rows {t['agg_rows']:,}")
    k = 500
    print(f"after scale-up (x{k}): {t['lines'] * k:,} lines, Sales Amount {t['amount'] * k:,.2f}, Units {t['units'] * k:,}, aggregation rows {t['agg_rows']:,}")
