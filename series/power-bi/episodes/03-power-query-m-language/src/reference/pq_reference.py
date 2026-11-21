#!/usr/bin/env python3
"""Python mirror of the Power Query queries in ../queries, step by step (same step names).

It is NOT an M engine. It is a second opinion: it follows what each M step is documented to do,
so we know what Power BI Desktop must load before Desktop opens, and the tests can prove that the
queries rebuild exactly the star schema of episode 1 from the messy monthly exports.

Usage:
    python pq_reference.py [--exports ../data/exports]     # prints the summary, rewrites expected/summary.json
"""
import argparse
import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNKNOWN_CUSTOMER_KEY = -1
TEXT_COLUMNS = ["OrderNumber", "CustomerName", "CustomerCity", "CustomerCountry", "StoreName",
                "StoreCountry", "Channel", "ProductName", "Subcategory", "Category", "Color"]


# ---------------------------------------------------------------- fnReadExport
def fn_read_export(content: bytes):
    """Csv.Document(';', 19 columns, UTF-8) -> PromoteHeaders -> NoTotals -> Cleaned -> Typed."""
    source = list(csv.reader(io.StringIO(content.decode("utf-8"), newline=""), delimiter=";"))
    source = [(r + [""] * 19)[:19] for r in source]                 # Columns = 19
    header, rows = source[0], source[1:]                             # Table.PromoteHeaders
    promoted = [dict(zip(header, r)) for r in rows]
    no_totals = [r for r in promoted if r["OrderNumber"] != "TOTAL"]
    out = []
    for r in no_totals:
        r = dict(r)
        # Cleaned (Table.TransformColumns)
        r["ProductCode"] = r["ProductCode"].strip().upper()
        r["CustomerCode"] = None if r["CustomerCode"].strip() == "" else r["CustomerCode"].strip()
        r["OrderDate"] = parse_dmy(r["OrderDate"])                    # Format "dd'/'MM'/'yyyy"
        r["ShipDate"] = parse_dmy(r["ShipDate"])
        # Typed (Table.TransformColumnTypes, culture pt-PT: decimal comma)
        r["LineNumber"] = int(r["LineNumber"])
        r["Quantity"] = int(r["Quantity"])
        r["UnitPrice"] = pt_number(r["UnitPrice"])
        r["UnitCost"] = pt_number(r["UnitCost"])
        out.append(r)
    return out


def parse_dmy(text: str) -> date:
    d, m, y = text.split("/")
    if len(d) != 2 or len(m) != 2 or len(y) != 4:
        raise ValueError(f"not dd/MM/yyyy: {text!r}")
    return date(int(y), int(m), int(d))


def pt_number(text: str) -> Decimal:
    if "." in text:
        raise ValueError(f"pt-PT numbers use a decimal comma: {text!r}")
    return Decimal(text.replace(",", "."))


# ---------------------------------------------------------------- SalesExport (staging, not loaded)
def sales_export(folder: Path, keep="newest", dedupe=True):
    files = sorted(Path(folder).iterdir())                           # Folder.Files
    csv_only = [f for f in files if f.suffix.lower() == ".csv"]      # Text.Lower([Extension]) = ".csv"
    combined = []
    for f in csv_only:                                               # Read + Table.Combine
        for r in fn_read_export(f.read_bytes()):
            r["SourceFile"] = f.name
            combined.append(r)
    if not dedupe:
        rows = combined
    else:
        # Newest = Table.Sort(SourceFile descending); Buffered = Table.Buffer; Deduped = Table.Distinct(keys)
        newest = sorted(combined, key=lambda r: r["SourceFile"], reverse=(keep == "newest"))
        seen, rows = set(), []
        for r in newest:
            k = (r["OrderNumber"], r["LineNumber"])
            if k not in seen:
                seen.add(k)
                rows.append(r)
    for r in rows:
        r.pop("SourceFile", None)                                    # Table.RemoveColumns
    return rows


# ---------------------------------------------------------------- fnDimension
def fn_dimension(source, business_key, attributes, key_name):
    columns = [{c: r[c] for c in [business_key] + attributes} for r in source]
    known = [r for r in columns if r[business_key] is not None]
    distinct, seen = [], set()
    for r in known:                                                  # Table.Distinct (all columns)
        t = tuple(r.values())
        if t not in seen:
            seen.add(t)
            distinct.append(r)
    ordered = sorted(distinct, key=lambda r: r[business_key])        # Table.Sort ascending
    return [{key_name: i, **r} for i, r in enumerate(ordered, start=1)]  # AddIndexColumn(1, 1)


def rename(rows, mapping):
    return [{mapping.get(k, k): v for k, v in r.items()} for r in rows]


def product(se):
    return rename(fn_dimension(se, "ProductCode", ["ProductName", "Subcategory", "Category", "Color"],
                               "ProductKey"), {"ProductName": "Product"})


def customer(se):
    dim = rename(fn_dimension(se, "CustomerCode", ["CustomerName", "CustomerCity", "CustomerCountry"],
                              "CustomerKey"),
                 {"CustomerName": "Customer", "CustomerCity": "City", "CustomerCountry": "Country"})
    unknown = {"CustomerKey": UNKNOWN_CUSTOMER_KEY, "CustomerCode": "", "Customer": "Unknown customer",
               "City": "Unknown", "Country": "Unknown"}
    return [unknown] + dim                                            # Table.InsertRows(.., 0, ..)


def store(se):
    return rename(fn_dimension(se, "StoreName", ["StoreCountry", "Channel"], "StoreKey"),
                  {"StoreName": "Store", "StoreCountry": "Country"})


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def date_table(se):
    dates = [r["OrderDate"] for r in se] + [r["ShipDate"] for r in se]
    first, last = date(min(dates).year, 1, 1), date(max(dates).year, 12, 31)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return [{
        "Date": d, "Year": d.year, "Quarter": f"Q{(d.month - 1) // 3 + 1}", "Month Number": d.month,
        "Month": MONTHS[d.month - 1], "Year Month": f"{d.year}-{d.month:02d}",
        "Year Month Number": d.year * 100 + d.month,
        "Day of Week Number": d.weekday() + 1,                       # Date.DayOfWeek(d, Day.Monday) + 1
        "Day of Week": DAYS[d.weekday()],
    } for d in days]


def sales(se, prod, cust, stor):
    pk = {p["ProductCode"]: p["ProductKey"] for p in prod}
    ck = {c["CustomerCode"]: c["CustomerKey"] for c in cust}
    sk = {s["Store"]: s["StoreKey"] for s in stor}
    out = []
    for r in se:                                                     # NestedJoin LeftOuter + Expand
        out.append({
            "OrderNumber": r["OrderNumber"], "LineNumber": r["LineNumber"],
            "OrderDate": r["OrderDate"], "ShipDate": r["ShipDate"],
            # null code never matches "" (Unknown row), so guests get null -> ReplaceValue -> -1
            "CustomerKey": ck.get(r["CustomerCode"]) if r["CustomerCode"] is not None else UNKNOWN_CUSTOMER_KEY,
            "ProductKey": pk.get(r["ProductCode"]), "StoreKey": sk.get(r["StoreName"]),
            "Quantity": r["Quantity"], "UnitPrice": r["UnitPrice"], "UnitCost": r["UnitCost"],
        })
    return out


def build(folder):
    se = sales_export(folder)
    prod, cust, stor = product(se), customer(se), store(se)
    return {"Sales": sales(se, prod, cust, stor), "Date": date_table(se), "Product": prod,
            "Customer": cust, "Store": stor}


def sales_amount(rows):
    return sum((r["Quantity"] * r["UnitPrice"] for r in rows), Decimal("0"))


def summary(folder):
    tables = build(folder)
    s = tables["Sales"]
    by_year = {}
    for r in s:
        by_year[r["OrderDate"].year] = by_year.get(r["OrderDate"].year, Decimal("0")) + r["Quantity"] * r["UnitPrice"]
    unknown = [r for r in s if r["CustomerKey"] == UNKNOWN_CUSTOMER_KEY]
    return {
        "files_read": len([f for f in Path(folder).iterdir() if f.suffix.lower() == ".csv"]),
        "rows_before_dedupe": len(sales_export(folder, dedupe=False)),
        "rows": {k: len(v) for k, v in tables.items()},
        "sales_amount": f"{sales_amount(s):.2f}",
        "sales_amount_by_year": {str(y): f"{v:.2f}" for y, v in sorted(by_year.items())},
        "units": sum(r["Quantity"] for r in s),
        "orders": len({r["OrderNumber"] for r in s}),
        "unknown_customer_sales": f"{sales_amount(unknown):.2f}",
        "date_range": [str(tables["Date"][0]["Date"]), str(tables["Date"][-1]["Date"])],
        "gotcha": {
            "no_dedupe_sales_amount": f"{sales_amount(sales_export(folder, dedupe=False)):.2f}",
            "keep_oldest_sales_amount": f"{sales_amount(sales_export(folder, keep='oldest')):.2f}",
            "keep_oldest_units": sum(r["Quantity"] for r in sales_export(folder, keep="oldest")),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", default=str(HERE.parent / "data" / "exports"))
    a = ap.parse_args()
    result = summary(a.exports)
    out = HERE / "expected" / "summary.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
