#!/usr/bin/env python3
"""reduce-demo: what the data reduction in the tuned model does to the columns, measured on the real CSV.

VertiPaq keeps one dictionary per column and one id per row. The more distinct values a column has, the bigger its
dictionary and the more bits every row needs (Learn: hash encoding assigns a numeric id to each unique value). This
script counts the distinct values of every column before and after the same steps the tuned model's Power Query
partition applies, and checks that the totals the reports show don't move:

  1. drop LineRef and Note (nothing in the model or the reports uses them)
  2. OrderDate = the date part of OrderTimestamp, then drop OrderTimestamp (a timestamp to the second is nearly unique)
  3. OrderNumber: strip the "SO-" prefix, keep a whole number (Learn: text with a prefix -> number)
  4. LineAmount = Quantity x UnitPrice, computed here (in Power Query in the model) instead of a DAX calculated column;
     UnitPrice is then dropped: no measure needs it any more

What it does NOT do: predict the size in megabytes. The bits per value is ceil(log2(distinct values)), the idea behind
the dictionary encoding, not VertiPaq's real number. Measure the real sizes in DAX query view (queries/01-*.dax).

    python reduce_demo.py <folder with sales_detail.csv> [--json out.json]
"""
import argparse
import csv
import json
import math
import re
from decimal import Decimal
from pathlib import Path


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def reduce_rows(header, rows):
    """The tuned model's Sales steps (mirror of model-after's Power Query partition)."""
    keep = [c for c in header if c not in ("LineRef", "Note", "OrderTimestamp", "OrderNumber", "UnitPrice")]
    out = []
    for r in rows:
        n = {"OrderNumber": str(int(r["OrderNumber"].split("-", 1)[1])), "OrderDate": r["OrderTimestamp"][:10]}
        n.update({c: r[c] for c in keep})
        n["LineAmount"] = str(Decimal(r["Quantity"]) * Decimal(r["UnitPrice"]))
        out.append(n)
    cols = ["OrderNumber", "OrderDate"] + keep + ["LineAmount"]
    return cols, out


def profile(header, rows):
    n = len(rows)
    result = {}
    for c in header:
        distinct = len({r[c] for r in rows})
        values = [r[c] for r in rows]
        # text that is always letters + digits ("SO-0000123"): a whole number would do (Learn: Optimize column data types)
        prefixed = all(re.fullmatch(r"[A-Za-z]{1,4}-?\d+", v) for v in values[:5000]) if values else False
        result[c] = {"distinct": distinct, "bits": max(1, math.ceil(math.log2(distinct))) if distinct > 1 else 1,
                     "uniqueness": round(distinct / n, 4) if n else 0, "prefixed_number": bool(prefixed)}
    return result


def totals(rows, amount):
    amt = sum(Decimal(amount(r)) for r in rows)
    return {"sales_amount": str(amt), "units": sum(int(r["Quantity"]) for r in rows),
            "orders": len({r["OrderNumber"] for r in rows}),
            "days": len({r.get("OrderDate") or r["OrderTimestamp"][:10] for r in rows})}


def run(folder: Path):
    header, rows = read(folder / "sales_detail.csv")
    cols, reduced = reduce_rows(header, rows)
    # the model-before partition also adds OrderDate (the relationship needs a date) and a DAX Line Amount column
    full = [dict(r, OrderDate=r["OrderTimestamp"][:10], LineAmount=str(Decimal(r["Quantity"]) * Decimal(r["UnitPrice"])))
            for r in rows]
    before = {"rows": len(rows), "columns": profile(header + ["OrderDate", "LineAmount"], full),
              "totals": totals(rows, lambda r: Decimal(r["Quantity"]) * Decimal(r["UnitPrice"]))}
    after = {"rows": len(reduced), "columns": profile(cols, reduced), "totals": totals(reduced, lambda r: r["LineAmount"])}
    for side in (before, after):
        side["sum_of_column_bits"] = sum(c["bits"] for c in side["columns"].values())
    return {"before": before, "after": after}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = run(Path(a.folder))
    for side in ("before", "after"):
        s = res[side]
        print(f"{side.upper()}: {s['rows']:,} rows, {len(s['columns'])} columns, {s['sum_of_column_bits']} bits per row in total")
        for name, c in s["columns"].items():
            print(f"  {name:<15} {c['distinct']:>9,} distinct  {c['bits']:>2} bits")
        print(f"  totals: {s['totals']}")
    same = res["before"]["totals"] == res["after"]["totals"]
    print("totals identical before and after" if same else "TOTALS DIFFER")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if same else 1)


if __name__ == "__main__":
    main()
