#!/usr/bin/env python3
"""Part B data: a store x month sales budget for 2025, derived deterministically from the order lines.

Budget = the 2025 actual of the store and month, scaled by a fixed factor per store, rounded to 100.
It is the 'file on the analyst's laptop' of the composite model story: a small Import table that doesn't live in the semantic model.
  python3 make_budget.py            # writes ../data/budget/budget.csv
  python3 make_budget.py --check    # fails if the committed file differs
"""
import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAR = HERE.parent / "data" / "star"
OUT = HERE.parent / "data" / "budget" / "budget.csv"
YEAR = "2025"
FACTOR = {1: "1.05", 2: "0.97", 3: "1.10", 4: "1.00", 5: "0.92"}   # per StoreKey: some stores beat the budget, some miss it


def build() -> list[list[str]]:
    stores = {r["StoreKey"]: r["Store"] for r in csv.DictReader((STAR / "dim_store.csv").open(encoding="utf-8"))}
    actual: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for r in csv.DictReader((STAR / "fact_sales.csv").open(encoding="utf-8")):
        if r["OrderDate"].startswith(YEAR):
            actual[(r["StoreKey"], r["OrderDate"][:7])] += Decimal(r["Quantity"]) * Decimal(r["UnitPrice"])
    rows = []
    for (key, ym), amount in sorted(actual.items(), key=lambda kv: (int(kv[0][0]), kv[0][1])):
        budget = (amount * Decimal(FACTOR[int(key)]) / 100).quantize(Decimal("1"), ROUND_HALF_UP) * 100
        rows.append([stores[key], ym, f"{budget:.2f}"])
    return rows


def render() -> str:
    lines = ["Store,Year Month,Budget Amount"] + [",".join(r) for r in build()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = render()
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("budget.csv is out of date, run make_budget.py")
        print("up to date")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT} ({len(text.splitlines()) - 1} rows)")
