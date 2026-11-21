#!/usr/bin/env python3
"""Python mirror of sql/01-create-and-load.sql: the same arithmetic, so the expected row counts and totals of the table are
known without a SQL Server. Row n (1-based) belongs to order o = (n-1)//5.

    python sql_mirror.py --rows 2000000            # per-year lines, orders and sales amount
    python sql_mirror.py --rows 2000000 --write expected/daily-2m.json
"""
import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

START = date(2023, 1, 1)
DAYS = 1461            # 2023-01-01 .. 2026-12-31
STORES = ["Contoso Madrid", "Contoso Lisboa", "Contoso Paris", "Contoso Porto", "Contoso Online"]
CATEGORIES = ["Bikes", "Clothing", "Accessories"]


def row(n: int) -> dict:
    o = (n - 1) // 5
    ts = datetime.combine(START + timedelta(days=(o * 7919) % DAYS), datetime.min.time()) + timedelta(seconds=(o * 104729) % 86400)
    store = (o * 31) % 5
    return {
        "SalesId": n, "OrderNumber": f"SO-{o + 1:07d}", "LineNumber": (n - 1) % 5 + 1, "OrderTimestamp": ts,
        "ModifiedDate": ts + timedelta(minutes=(o * 37) % 600),
        "StoreName": STORES[store], "Channel": "Online" if store == 4 else "Store", "Category": CATEGORIES[(n * 17) % 3],
        "Quantity": 1 + (n * 13) % 5, "UnitPriceCents": 2000 + (n * 7919) % 98000,
    }


def daily(rows: int) -> dict:
    """{ 'YYYY-MM-DD': [order lines, sales amount in cents] }"""
    out = defaultdict(lambda: [0, 0])
    for n in range(1, rows + 1):
        o = (n - 1) // 5
        d = START + timedelta(days=(o * 7919) % DAYS)
        q = 1 + (n * 13) % 5
        p = 2000 + (n * 7919) % 98000
        a = out[d.isoformat()]
        a[0] += 1
        a[1] += q * p
    return dict(sorted(out.items()))


def by_year(daily_rows: dict) -> dict:
    out = defaultdict(lambda: [0, 0])
    for d, (lines, cents) in daily_rows.items():
        out[int(d[:4])][0] += lines
        out[int(d[:4])][1] += cents
    return dict(out)


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2_000_000)
    ap.add_argument("--write")
    a = ap.parse_args()
    d = daily(a.rows)
    for y, (lines, cents) in by_year(d).items():
        print(f"{y}  order lines {lines:>9,}  sales amount {money(cents):>14}")
    tl, tc = sum(v[0] for v in d.values()), sum(v[1] for v in d.values())
    print(f"all   order lines {tl:>9,}  sales amount {money(tc):>14}  orders {a.rows // 5:,}  days {len(d)}")
    if a.write:
        Path(a.write).parent.mkdir(parents=True, exist_ok=True)
        Path(a.write).write_text(json.dumps({"rows": a.rows, "start": START.isoformat(), "daily": d}, separators=(",", ":")) + "\n")
        print("wrote", a.write)


if __name__ == "__main__":
    main()
