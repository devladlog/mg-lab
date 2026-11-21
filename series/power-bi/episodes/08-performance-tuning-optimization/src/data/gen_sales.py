#!/usr/bin/env python3
"""Generate the Contoso Bikes order-line export that has outgrown the report (all data fictional, deterministic).

Writes five CSV files into --out:
  sales_detail.csv   one row per order line: text order number with a prefix, a timestamp to the second, a per-line
                     reference and a free-text note (the columns that make an Import model big)
  product.csv, customer.csv, store.csv, date.csv   the dimensions

    python gen_sales.py --rows 2000000 --out C:\\ContosoBikesPerf      # the demo size
    python gen_sales.py --rows 20000 --out ./tmp                       # what the tests use

The same --rows and --seed always give the same files (random.Random with a fixed seed), so the expected numbers in
expected/ can be checked.
"""
import argparse
import csv
import datetime as dt
import random
from pathlib import Path

START, END = dt.date(2023, 1, 1), dt.date(2025, 12, 31)       # order dates
DATE_FROM, DATE_TO = dt.date(2023, 1, 1), dt.date(2026, 1, 31)  # date dimension (covers the ship dates)

STORES = [(1, "Contoso Lisboa", "Portugal", "Store"), (2, "Contoso Porto", "Portugal", "Store"),
          (3, "Contoso Madrid", "Spain", "Store"), (4, "Contoso Paris", "France", "Store"),
          (5, "Contoso Online", "Online", "Online")]
PRODUCTS = [
    ("Roadster 100", "Bikes", "Road Bikes", 899.00), ("Roadster 200", "Bikes", "Road Bikes", 1299.00),
    ("Roadster 300", "Bikes", "Road Bikes", 1899.00), ("Trail Runner", "Bikes", "Mountain Bikes", 1099.00),
    ("Trail Runner Pro", "Bikes", "Mountain Bikes", 1599.00), ("City Glide", "Bikes", "Commuter Bikes", 649.00),
    ("City Glide E", "Bikes", "Commuter Bikes", 1499.00), ("Helmet Air", "Accessories", "Helmets", 79.00),
    ("Helmet Pro", "Accessories", "Helmets", 129.00), ("Lock Chain", "Accessories", "Locks", 39.00),
    ("Lock U", "Accessories", "Locks", 49.00), ("Light Set", "Accessories", "Lights", 29.00),
    ("Bottle Cage", "Accessories", "Bottles", 12.00), ("Jersey Team", "Clothing", "Jerseys", 69.00),
    ("Jersey Rain", "Clothing", "Jerseys", 89.00), ("Bib Shorts", "Clothing", "Shorts", 99.00),
    ("Gloves Grip", "Clothing", "Gloves", 25.00), ("Socks Pair", "Clothing", "Socks", 9.00),
    ("Cap Tour", "Clothing", "Caps", 19.00)]
CITIES = [("Lisboa", "Portugal"), ("Porto", "Portugal"), ("Braga", "Portugal"), ("Madrid", "Spain"),
          ("Sevilla", "Spain"), ("Paris", "France"), ("Lyon", "France")]
NOTES = ["Gift order", "Call before delivery", "Leave at reception", "Fragile", "Second delivery attempt",
         "Customer asked for invoice", "Store pickup", "Express shipping"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def dimensions(out: Path, customers: int):
    write(out / "store.csv", ["StoreKey", "Store", "Country", "Channel"], STORES)
    write(out / "product.csv", ["ProductKey", "Product", "Category", "Subcategory", "ListPrice"],
          [(i + 1, n, c, s, f"{p:.2f}") for i, (n, c, s, p) in enumerate(PRODUCTS)])
    write(out / "customer.csv", ["CustomerKey", "CustomerCode", "Customer", "City", "Country"],
          [(k, f"C{k:05d}", f"Customer {k:05d}", *CITIES[k % len(CITIES)]) for k in range(1, customers + 1)])
    days = (DATE_TO - DATE_FROM).days + 1
    rows = []
    for i in range(days):
        d = DATE_FROM + dt.timedelta(days=i)
        rows.append((d.isoformat(), d.year, f"Q{(d.month - 1) // 3 + 1}", d.month, MONTHS[d.month - 1],
                     f"{d.year}-{d.month:02d}", d.year * 100 + d.month))
    write(out / "date.csv", ["Date", "Year", "Quarter", "MonthNumber", "Month", "YearMonth", "YearMonthNumber"], rows)


def sales_rows(rows: int, seed: int, customers: int):
    rng = random.Random(seed)
    span = (END - START).days + 1
    made, order = 0, 0
    while made < rows:
        order += 1
        day = START + dt.timedelta(days=rng.randrange(span))
        stamp = dt.datetime.combine(day, dt.time(rng.randrange(8, 21), rng.randrange(60), rng.randrange(60)))
        ship = day + dt.timedelta(days=rng.randrange(1, 6))
        customer, store = rng.randrange(1, customers + 1), rng.randrange(1, len(STORES) + 1)
        note = f"{rng.choice(NOTES)} {rng.randrange(10**6):06d}" if rng.random() < 0.3 else ""
        for line in range(1, rng.randrange(1, 5) + 1):
            if made == rows:
                break
            product = rng.randrange(1, len(PRODUCTS) + 1)
            price = round(PRODUCTS[product - 1][3] * (1 - rng.choice((0, 0, 0.05, 0.10, 0.15))), 2)
            made += 1
            yield (f"SO-{order:07d}", stamp.isoformat(timespec="seconds"), ship.isoformat(), customer, product,
                   store, rng.randrange(1, 6), f"{price:.2f}", f"{price * 0.6:.2f}", f"{rng.getrandbits(48):012x}",
                   note)


SALES_HEADER = ["OrderNumber", "OrderTimestamp", "ShipDate", "CustomerKey", "ProductKey", "StoreKey", "Quantity",
                "UnitPrice", "UnitCost", "LineRef", "Note"]


def generate(out: Path, rows: int, seed: int = 20260101, customers: int = 5000):
    out.mkdir(parents=True, exist_ok=True)
    dimensions(out, customers)
    write(out / "sales_detail.csv", SALES_HEADER, sales_rows(rows, seed, customers))
    return out / "sales_detail.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2_000_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--customers", type=int, default=5000)
    a = ap.parse_args()
    path = generate(Path(a.out), a.rows, a.seed, a.customers)
    print(f"wrote {a.rows:,} order lines + 4 dimensions to {a.out} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
