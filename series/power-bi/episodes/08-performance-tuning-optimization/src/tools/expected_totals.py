#!/usr/bin/env python3
"""expected-totals: the numbers the cards of BOTH reports must show for a generated export (streams the CSV, so it
works for the 2,000,000-line demo file too):  python expected_totals.py <folder with sales_detail.csv> [--json]"""
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

ONLINE_STORE = "5"      # StoreKey of Contoso Online (see gen_sales.STORES)


def totals(folder: Path):
    amount = cost = Decimal(0)
    units = lines = 0
    orders = set()
    online = Decimal(0)
    by_year = {}
    with open(folder / "sales_detail.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            q = int(r["Quantity"])
            a, c = q * Decimal(r["UnitPrice"]), q * Decimal(r["UnitCost"])
            amount, cost, units, lines = amount + a, cost + c, units + q, lines + 1
            orders.add(r["OrderNumber"])
            if r["StoreKey"] == ONLINE_STORE:
                online += a
            y = r["OrderTimestamp"][:4]
            by_year[y] = by_year.get(y, Decimal(0)) + a
    prior = by_year.get("2024"), by_year.get("2023")
    return {"lines": lines, "sales_amount": str(amount), "total_cost": str(cost),
            "margin_percent": f"{(amount - cost) / amount * 100:.1f}", "units": units, "orders": len(orders),
            "online_sales": str(online), "sales_2024": str(prior[0]), "sales_2023": str(prior[1]),
            "yoy_2024_percent": f"{(prior[0] - prior[1]) / prior[1] * 100:.1f}"}


if __name__ == "__main__":
    if len(sys.argv) < 2 or not Path(sys.argv[1], "sales_detail.csv").exists():
        print(__doc__)
        sys.exit(2)
    t = totals(Path(sys.argv[1]))
    print(json.dumps(t, indent=2) if "--json" in sys.argv else "\n".join(f"{k:<18}{v}" for k, v in t.items()))
