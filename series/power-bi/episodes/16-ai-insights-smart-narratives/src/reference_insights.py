#!/usr/bin/env python3
"""reference-insights: what the AI visuals should roughly say, computed with plain Python.

This is a DIRECTIONAL reference, not a re-implementation. Power BI fits a regression (key influencers) and
runs SR-CNN (anomaly detection); this file only computes the simple comparison Learn uses to explain the
result, so you can tell on camera whether the visual agrees with the data.

  influencers()  for each Explain by value: rate of the target state inside the value, rate in all other
                 values, and the ratio ("x times more likely"), the way the Learn page describes it
  anomalies()    days whose daily sales sit far from the median of their 28-day neighbourhood (robust z-score)
  narrative()    the sentences the Narrative measures in the model should produce, for a calendar year

Usage:
    python reference_insights.py --star <star folder> [--outcome "Survey Rating"] [--target Low]
"""
import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date

from ai_readiness import COLUMN, daily_sales, read_csv

DEFAULT_EXPLAIN = ["Channel", "Store Country", "Customer Country", "Contains Bike", "Lines", "Delivery"]


def influencers(rows, outcome, target, explain, min_n=30):
    """Ranked list of {field, value, n, rate_in, rate_out, lift}. Values with fewer than min_n rows are skipped."""
    col = COLUMN[outcome]
    hit = [r[col] == target for r in rows]
    result = []
    for field in explain:
        c = COLUMN[field]
        n_by, hit_by = Counter(), Counter()
        for r, h in zip(rows, hit):
            n_by[r[c]] += 1
            hit_by[r[c]] += h
        for value, n in n_by.items():
            n_out = len(rows) - n
            if n < min_n or n_out < min_n:
                continue
            rate_in = hit_by[value] / n
            rate_out = (sum(hit) - hit_by[value]) / n_out
            lift = rate_in / rate_out if rate_out else float("inf")
            result.append({"field": field, "value": value, "n": n, "rate_in": rate_in,
                           "rate_out": rate_out, "lift": lift})
    return sorted(result, key=lambda x: -x["lift"])


def anomalies(points, window=14, threshold=4.0):
    """points: [(iso date, value)]. Returns [(date, value, robust z)] sorted by |z| descending."""
    values = [v for _, v in points]
    out = []
    for i, (d, v) in enumerate(points):
        near = values[max(0, i - window): i + window + 1]
        med = statistics.median(near)
        mad = statistics.median(abs(x - med) for x in near) or 1e-9
        z = 0.6745 * (v - med) / mad
        if abs(z) >= threshold:
            out.append((d, v, round(z, 1)))
    return sorted(out, key=lambda x: -abs(x[2]))


def narrative(star_dir, year):
    """Expected text of the three Narrative measures for one calendar year (no other filters)."""
    from pathlib import Path
    star = Path(star_dir)
    category = {r["ProductKey"]: r["Category"] for r in read_csv(star / "dim_product.csv")}
    total, prior, by_cat = 0.0, 0.0, defaultdict(float)
    for r in read_csv(star / "fact_sales.csv"):
        amount = float(r["Quantity"]) * float(r["UnitPrice"])
        y = date.fromisoformat(r["OrderDate"]).year
        if y == year:
            total += amount
            by_cat[category[r["ProductKey"]]] += amount
        elif y == year - 1:
            prior += amount
    sales = f"Sales were {total:,.0f} in the selected period."
    if prior:
        g = (total - prior) / prior
        yoy = f"That is {abs(g):.1%} {'above' if g >= 0 else 'below'} the same period last year."
    else:
        yoy = "There is no prior-year period to compare with."
    top = f"{max(by_cat, key=by_cat.get)} leads the mix." if by_cat else None
    return {"Narrative Sales": sales, "Narrative YoY": yoy, "Narrative Top Category": top}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--outcome", default="Survey Rating")
    ap.add_argument("--target", default="Low")
    ap.add_argument("--year", type=int, default=2025)
    a = ap.parse_args(argv)
    from pathlib import Path
    rows = read_csv(Path(a.star) / "order_profile.csv")
    print(f"Influencers on {a.outcome} = {a.target} (ratio of the rate inside the value to the rate in all other values)")
    for x in influencers(rows, a.outcome, a.target, DEFAULT_EXPLAIN)[:8]:
        print(f"  {x['field']} is {x['value']}: {x['rate_in']:.1%} vs {x['rate_out']:.1%} -> {x['lift']:.2f}x (n={x['n']})")
    print("Candidate anomaly days (robust z, directional only)")
    for d, v, z in anomalies(daily_sales(a.star))[:5]:
        print(f"  {d}  {v:,.0f}  z={z}")
    print(f"Expected narrative text for {a.year}")
    for k, v in narrative(a.star, a.year).items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
