#!/usr/bin/env python3
"""Build the order-level table that the AI visuals analyse: one row per order.

    star/fact_sales.csv + dim_product.csv + dim_customer.csv + dim_store.csv  ->  star/order_profile.csv

Why a separate table: the key influencers visual runs at the grain of the table that holds the metric
(Microsoft Learn: "the analysis runs on the table level of the field that's being analyzed"), and every
explanatory field must be an attribute of that grain. Order lines are too fine; one row per order is right.

Derived from the data (plain rules):
    Order Size  Small < 100, Medium < 1,000, Large >= 1,000 (sum of quantity x unit price)
    Delivery    Fast when ship date - order date <= 3 days, Slow above 3

SIMULATED, and labelled as such: Survey Rating (High or Low). The Contoso export has no customer feedback, so the
lab simulates one, the way Microsoft's key influencers tutorial uses a sample feedback file. The odds of a Low rating
are planted: a base rate, higher for Slow delivery and higher for Online orders. The planted effect lets the demo and
the tests check that the visual finds what was put in. It is not a finding about any real business.

Usage:
    python build_order_profile.py [--star star]
"""
import argparse
import csv
import random
from datetime import date
from pathlib import Path

FIELDS = ["OrderNumber", "OrderDate", "Channel", "StoreCountry", "CustomerCountry", "ContainsBike",
          "Lines", "Units", "OrderValue", "OrderSize", "ShipDays", "Delivery", "SurveyRating"]
LARGE_FROM = 1000.0
MEDIUM_FROM = 100.0
SLOW_ABOVE_DAYS = 3
SEED = 42
BASE_LOW = 0.06          # probability of a Low rating for a Fast, in-store order
SLOW_FACTOR = 2.8        # planted: Slow delivery multiplies the odds
ONLINE_FACTOR = 1.8      # planted: Online orders multiply the odds


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def order_size(value):
    if value >= LARGE_FROM:
        return "Large"
    return "Medium" if value >= MEDIUM_FROM else "Small"


def low_rating_probability(delivery, channel):
    p = BASE_LOW
    if delivery == "Slow":
        p *= SLOW_FACTOR
    if channel == "Online":
        p *= ONLINE_FACTOR
    return p


def build_profile(star_dir, seed=SEED):
    star = Path(star_dir)
    fact = _read(star / "fact_sales.csv")
    category = {r["ProductKey"]: r["Category"] for r in _read(star / "dim_product.csv")}
    cust_country = {r["CustomerKey"]: r["Country"] for r in _read(star / "dim_customer.csv")}
    stores = {r["StoreKey"]: r for r in _read(star / "dim_store.csv")}

    orders = {}
    for r in fact:
        o = orders.setdefault(r["OrderNumber"], {"lines": [], "r": r})
        o["lines"].append(r)

    rng = random.Random(f"{seed}-survey-rating")
    out = []
    for number in sorted(orders):
        lines, first = orders[number]["lines"], orders[number]["r"]
        value = round(sum(int(x["Quantity"]) * float(x["UnitPrice"]) for x in lines), 2)
        days = (date.fromisoformat(first["ShipDate"]) - date.fromisoformat(first["OrderDate"])).days
        store = stores[first["StoreKey"]]
        delivery = "Slow" if days > SLOW_ABOVE_DAYS else "Fast"
        low = rng.random() < low_rating_probability(delivery, store["Channel"])
        out.append({
            "OrderNumber": number,
            "OrderDate": first["OrderDate"],
            "Channel": store["Channel"],
            "StoreCountry": store["Country"],
            "CustomerCountry": cust_country[first["CustomerKey"]],
            "ContainsBike": "Yes" if any(category[x["ProductKey"]] == "Bikes" for x in lines) else "No",
            "Lines": len(lines),
            "Units": sum(int(x["Quantity"]) for x in lines),
            "OrderValue": f"{value:.2f}",
            "OrderSize": order_size(value),
            "ShipDays": days,
            "Delivery": delivery,
            "SurveyRating": "Low" if low else "High",
        })
    return out


def write_profile(rows, star_dir):
    path = Path(star_dir) / "order_profile.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", default=str(Path(__file__).parent / "star"))
    a = ap.parse_args()
    path = write_profile(build_profile(a.star), a.star)
    print(f"order_profile {len(_read(path)):6} rows -> {path}")


if __name__ == "__main__":
    main()
