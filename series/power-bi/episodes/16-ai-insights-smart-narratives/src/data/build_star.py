#!/usr/bin/env python3
"""Turn the denormalized sales export into a star schema: one fact table + four dimensions.

    raw/sales_export.csv  ->  star/fact_sales.csv
                              star/dim_date.csv
                              star/dim_product.csv   (category + subcategory flattened in: no snowflake)
                              star/dim_customer.csv  (with an explicit "Unknown customer" row, key -1)
                              star/dim_store.csv

This is the "warehouse" step. Microsoft's star schema guidance recommends doing this upstream
(a warehouse + ETL) when it gets complex; for a small export you'd do the same in Power Query.

Usage:
    python build_star.py [--src raw/sales_export.csv] [--out star]
"""
import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

UNKNOWN_CUSTOMER_KEY = -1
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def read_export(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_dim(rows, business_key, attrs, start_key=1):
    """Assign a surrogate key per distinct business key (sorted, so keys are stable)."""
    seen = {}
    for r in rows:
        bk = r[business_key]
        if bk and bk not in seen:
            seen[bk] = {a_out: r[a_in] for a_out, a_in in attrs}
    dim, lookup = [], {}
    for i, bk in enumerate(sorted(seen), start=start_key):
        lookup[bk] = i
        dim.append({"key": i, "bk": bk, **seen[bk]})
    return dim, lookup


def build_date(first: date, last: date):
    """One row per day, full calendar years (a requirement for a date table)."""
    d, out = date(first.year, 1, 1), []
    end = date(last.year, 12, 31)
    while d <= end:
        out.append({
            "Date": d.isoformat(),
            "Year": d.year,
            "Quarter": f"Q{(d.month - 1) // 3 + 1}",
            "Month Number": d.month,
            "Month": MONTHS[d.month - 1],
            "Year Month": f"{d.year}-{d.month:02d}",
            "Year Month Number": d.year * 100 + d.month,
            "Day of Week Number": d.isoweekday(),
            "Day of Week": DAYS[d.weekday()],
        })
        d += timedelta(days=1)
    return out


def build(rows):
    products, prod_key = build_dim(rows, "ProductCode", [
        ("Product", "ProductName"), ("Subcategory", "Subcategory"),
        ("Category", "Category"), ("Color", "Color")])
    customers, cust_key = build_dim(rows, "CustomerCode", [
        ("Customer", "CustomerName"), ("City", "CustomerCity"), ("Country", "CustomerCountry")])
    stores, store_key = build_dim(rows, "StoreName", [("Country", "StoreCountry"), ("Channel", "Channel")])

    customers.insert(0, {"key": UNKNOWN_CUSTOMER_KEY, "bk": "", "Customer": "Unknown customer",
                         "City": "Unknown", "Country": "Unknown"})

    fact = []
    for r in rows:
        fact.append({
            "OrderNumber": r["OrderNumber"],
            "LineNumber": int(r["LineNumber"]),
            "OrderDate": r["OrderDate"],
            "ShipDate": r["ShipDate"],
            "CustomerKey": cust_key.get(r["CustomerCode"], UNKNOWN_CUSTOMER_KEY),
            "ProductKey": prod_key[r["ProductCode"]],
            "StoreKey": store_key[r["StoreName"]],
            "Quantity": int(r["Quantity"]),
            "UnitPrice": r["UnitPrice"],
            "UnitCost": r["UnitCost"],
        })

    all_dates = [date.fromisoformat(x) for r in rows for x in (r["OrderDate"], r["ShipDate"])]
    dates = build_date(min(all_dates), max(all_dates))

    return {
        "fact_sales": fact,
        "dim_date": dates,
        "dim_product": [{"ProductKey": p["key"], "ProductCode": p["bk"], "Product": p["Product"],
                         "Subcategory": p["Subcategory"], "Category": p["Category"], "Color": p["Color"]}
                        for p in products],
        "dim_customer": [{"CustomerKey": c["key"], "CustomerCode": c["bk"], "Customer": c["Customer"],
                          "City": c["City"], "Country": c["Country"]} for c in customers],
        "dim_store": [{"StoreKey": s["key"], "Store": s["bk"], "Country": s["Country"],
                       "Channel": s["Channel"]} for s in stores],
    }


def write(tables, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"{name:13} {len(rows):6} rows")


def main():
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(here / "raw" / "sales_export.csv"))
    ap.add_argument("--out", default=str(here / "star"))
    a = ap.parse_args()
    write(build(read_export(a.src)), a.out)


if __name__ == "__main__":
    main()
