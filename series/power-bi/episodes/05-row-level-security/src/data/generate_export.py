#!/usr/bin/env python3
"""Generate a fictional, denormalized sales export ("one big table") for Contoso Bikes.

Deterministic: the same seed always produces byte-identical output, so the CSV can be
committed and the tests can regenerate it and compare.

Usage:
    python generate_export.py [--out raw/sales_export.csv] [--seed 42]
"""
import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

START = date(2024, 1, 1)
END = date(2025, 12, 31)

# category -> subcategory -> list of (code, name, color, list price, unit cost)
CATALOG = {
    "Bikes": {
        "Road Bikes": [
            ("BK-R-100", "Road 100", "Red", 899.00, 540.00),
            ("BK-R-200", "Road 200", "Black", 1299.00, 760.00),
            ("BK-R-300", "Road 300 Carbon", "White", 2499.00, 1390.00),
        ],
        "Mountain Bikes": [
            ("BK-M-100", "Trail 100", "Green", 749.00, 455.00),
            ("BK-M-200", "Trail 200", "Black", 1149.00, 690.00),
            ("BK-M-300", "Enduro 300", "Orange", 2199.00, 1240.00),
        ],
        "City Bikes": [
            ("BK-C-100", "Urban 100", "Blue", 499.00, 300.00),
            ("BK-C-200", "Urban 200 E-Assist", "Grey", 1799.00, 1080.00),
        ],
    },
    "Accessories": {
        "Helmets": [
            ("AC-H-010", "Helmet Sport", "Red", 59.90, 22.00),
            ("AC-H-020", "Helmet Commuter", "Black", 79.90, 31.00),
        ],
        "Lights": [
            ("AC-L-010", "Front Light 400", "Black", 34.90, 12.50),
            ("AC-L-020", "Rear Light Radar", "Black", 129.00, 61.00),
        ],
        "Locks": [
            ("AC-K-010", "U-Lock", "Yellow", 44.90, 17.00),
            ("AC-K-020", "Folding Lock", "Black", 89.90, 38.00),
        ],
        "Bottles": [
            ("AC-B-010", "Bottle 750 ml", "Blue", 9.90, 2.80),
        ],
    },
    "Clothing": {
        "Jerseys": [
            ("CL-J-010", "Jersey Classic", "Blue", 49.90, 18.00),
            ("CL-J-020", "Jersey Aero", "White", 89.90, 35.00),
        ],
        "Gloves": [
            ("CL-G-010", "Gloves Summer", "Black", 24.90, 8.00),
            ("CL-G-020", "Gloves Winter", "Black", 39.90, 14.50),
        ],
    },
}

STORES = [
    ("Contoso Lisboa", "Portugal", "Store"),
    ("Contoso Porto", "Portugal", "Store"),
    ("Contoso Madrid", "Spain", "Store"),
    ("Contoso Paris", "France", "Store"),
    ("Contoso Online", "Portugal", "Online"),
]

CITIES = [
    ("Lisboa", "Portugal"), ("Porto", "Portugal"), ("Braga", "Portugal"), ("Coimbra", "Portugal"),
    ("Madrid", "Spain"), ("Valencia", "Spain"), ("Sevilla", "Spain"),
    ("Paris", "France"), ("Lyon", "France"), ("Lille", "France"),
]

FIRST = ["Alex", "Sam", "Jordan", "Robin", "Taylor", "Casey", "Morgan", "Jamie", "Avery", "Riley",
         "Noa", "Ari", "Kai", "Remy", "Sasha", "Dani", "Charlie", "Quinn", "Rui", "Ines"]
LAST = ["Demo", "Sample", "Example", "Tester", "Placeholder", "Fiction", "Mock", "Lab", "Draft", "Pilot"]

N_CUSTOMERS = 300
GUEST_SHARE = 0.03          # orders without a customer (guest checkout) -> unknown member in the star
SEASON = [0.55, 0.6, 0.85, 1.05, 1.25, 1.35, 1.4, 1.25, 1.05, 0.8, 0.7, 0.95]  # Jan..Dec
GROWTH_2025 = 1.12

HEADER = ["OrderNumber", "LineNumber", "OrderDate", "ShipDate", "CustomerCode", "CustomerName",
          "CustomerCity", "CustomerCountry", "StoreName", "StoreCountry", "Channel",
          "ProductCode", "ProductName", "Subcategory", "Category", "Color",
          "Quantity", "UnitPrice", "UnitCost"]


def products():
    for category, subs in CATALOG.items():
        for sub, items in subs.items():
            for code, name, color, price, cost in items:
                yield {"code": code, "name": name, "sub": sub, "cat": category,
                       "color": color, "price": price, "cost": cost}


def customers(rng):
    out = []
    for i in range(1, N_CUSTOMERS + 1):
        city, country = rng.choice(CITIES)
        out.append({"code": f"C{i:04d}", "name": f"{rng.choice(FIRST)} {rng.choice(LAST)} {i:03d}",
                    "city": city, "country": country})
    return out


def generate(seed=42):
    rng = random.Random(seed)
    prods = list(products())
    bikes = [p for p in prods if p["cat"] == "Bikes"]
    other = [p for p in prods if p["cat"] != "Bikes"]
    custs = customers(rng)
    rows = []
    order_no = 0
    d = START
    while d <= END:
        rate = 3.2 * SEASON[d.month - 1] * (GROWTH_2025 if d.year == 2025 else 1.0)
        n_orders = sum(1 for _ in range(8) if rng.random() < rate / 8)
        for _ in range(n_orders):
            order_no += 1
            store = rng.choice(STORES)
            cust = None if rng.random() < GUEST_SHARE else rng.choice(custs)
            ship = d + timedelta(days=rng.randint(1, 5))
            n_lines = rng.choice([1, 1, 1, 2, 2, 3])
            chosen = []
            for line in range(1, n_lines + 1):
                pool = bikes if (line == 1 and rng.random() < 0.45) else other
                p = rng.choice([x for x in pool if x not in chosen] or pool)
                chosen.append(p)
                qty = 1 if p["cat"] == "Bikes" else rng.choice([1, 1, 2, 2, 3, 4])
                discount = rng.choice([0, 0, 0, 0.05, 0.10])
                price = round(p["price"] * (1 - discount), 2)
                rows.append([
                    f"SO{order_no:06d}", line, d.isoformat(), ship.isoformat(),
                    cust["code"] if cust else "", cust["name"] if cust else "",
                    cust["city"] if cust else "", cust["country"] if cust else "",
                    store[0], store[1], store[2],
                    p["code"], p["name"], p["sub"], p["cat"], p["color"],
                    qty, f"{price:.2f}", f"{p['cost']:.2f}",
                ])
        d += timedelta(days=1)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "raw" / "sales_export.csv"))
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = generate(a.seed)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
