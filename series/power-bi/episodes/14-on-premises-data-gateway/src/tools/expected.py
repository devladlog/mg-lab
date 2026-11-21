#!/usr/bin/env python3
"""What the gateway refresh must load: totals and per-store sales straight from the star CSVs (standard library only).
The CSVs are episode 11's (the same Contoso Bikes data as episodes 1-12); a test compares them byte for byte when episode 11 is next to this one."""
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent / "data" / "star"


def load():
    stores = {r["StoreKey"]: r["Store"] for r in csv.DictReader((STAR / "dim_store.csv").open(encoding="utf-8"))}
    amount = defaultdict(Decimal)
    lines = defaultdict(int)
    for r in csv.DictReader((STAR / "fact_sales.csv").open(encoding="utf-8")):
        store = stores[r["StoreKey"]]
        amount[store] += Decimal(r["Quantity"]) * Decimal(r["UnitPrice"])
        lines[store] += 1
    return amount, lines


def totals():
    amount, lines = load()
    return {"lines": sum(lines.values()), "amount": sum(amount.values()), "stores": len(amount)}


if __name__ == "__main__":
    amount, lines = load()
    t = totals()
    print(f"{t['lines']:,} order lines, Sales Amount {t['amount']:,.2f}, {t['stores']} stores")
    for store in sorted(amount):
        print(f"  {store:<16} {amount[store]:>14,.2f}  {lines[store]:>5,} lines")
