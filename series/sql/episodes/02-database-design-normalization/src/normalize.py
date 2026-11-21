"""From a flat bookings export to a third-normal-form design, with the evidence.

    python src/normalize.py                         # design report: keys, dependencies, conflicts, tables
    python src/normalize.py --write-sql src/sql/02-data.sql --write-csv data/normalized

Steps (each one is a function the tests call):
1. ``to_1nf``      - split the repeating group (CourseCodes "SQL101|SQL201" ...) into one row per booking line
2. ``check_design`` - test the functional dependencies the business told us about against the data
3. ``normalize``   - split into Company, Customer, Course, Booking, BookingLine; resolve conflicting values
4. ``rebuild``     - join everything back: must give the (resolved) 1NF rows again, a lossless decomposition
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLAT_CSV = HERE.parent / "data" / "bookings_flat.csv"

LIST_COLUMNS = {"CourseCodes": "CourseCode", "CourseTitles": "CourseTitle",
                "ListPrices": "ListPrice", "PricesPaid": "PricePaid"}
ONE_NF_COLUMNS = ["BookingRef", "BookingDate", "CustomerEmail", "CustomerName", "Company", "CompanyCity",
                  "CourseCode", "CourseTitle", "ListPrice", "PricePaid"]

# What the business says determines what. lhs -> rhs columns.
DESIGN_FDS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("BookingRef",), ("BookingDate", "CustomerEmail")),
    (("CustomerEmail",), ("CustomerName", "Company")),
    (("Company",), ("CompanyCity",)),
    (("CourseCode",), ("CourseTitle", "ListPrice")),
    (("BookingRef", "CourseCode"), ("PricePaid",)),
]


# ---------------------------------------------------------------- 1NF
def read_flat(path: Path = FLAT_CSV) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_1nf(flat: list[dict]) -> list[dict]:
    """One row per (BookingRef, CourseCode). The four list columns must line up item by item."""
    rows = []
    for r in flat:
        lists = {col: r[col].split("|") for col in LIST_COLUMNS}
        lengths = {len(v) for v in lists.values()}
        if len(lengths) != 1:
            raise ValueError(f"{r['BookingRef']}: list columns have different lengths "
                             f"({', '.join(f'{c}={len(v)}' for c, v in lists.items())})")
        for i in range(lengths.pop()):
            row = {c: r[c] for c in ONE_NF_COLUMNS[:6]}
            for col, single in LIST_COLUMNS.items():
                value = lists[col][i].strip()
                row[single] = Decimal(value) if single in ("ListPrice", "PricePaid") else value
            rows.append(row)
    return rows


# ---------------------------------------------------------------- functional dependencies
def fd_violations(rows: list[dict], lhs: tuple[str, ...], rhs: str) -> dict[tuple, list]:
    """{lhs value: [distinct rhs values]} for every lhs value that maps to more than one rhs value."""
    seen: dict[tuple, set] = defaultdict(set)
    for r in rows:
        seen[tuple(r[c] for c in lhs)].add(r[rhs])
    return {k: sorted(v, key=str) for k, v in seen.items() if len(v) > 1}


def is_unique(rows: list[dict], cols: tuple[str, ...]) -> bool:
    return len({tuple(r[c] for c in cols) for r in rows}) == len(rows)


def candidate_keys(rows: list[dict], columns: list[str], max_size: int = 2) -> list[tuple[str, ...]]:
    """Minimal column sets whose values are unique in this data (a hint, not a proof: data can't prove a key)."""
    keys: list[tuple[str, ...]] = []
    for size in range(1, max_size + 1):
        for cols in combinations(columns, size):
            if any(set(k) <= set(cols) for k in keys):
                continue
            if is_unique(rows, cols):
                keys.append(cols)
    return keys


def check_design(rows: list[dict]) -> list[dict]:
    """Every declared dependency, whether the data obeys it, and the conflicting values when it doesn't."""
    out = []
    for lhs, rhs_cols in DESIGN_FDS:
        for rhs in rhs_cols:
            v = fd_violations(rows, lhs, rhs)
            out.append({"lhs": lhs, "rhs": rhs, "holds": not v, "conflicts": v})
    return out


def classify(lhs: tuple[str, ...], key: tuple[str, ...]) -> str:
    """Why a dependency breaks a normal form, relative to the 1NF table's key."""
    if set(lhs) == set(key):
        return "full (fine)"
    if set(lhs) < set(key):
        return "partial: breaks 2NF"
    return "transitive: breaks 3NF"


# ---------------------------------------------------------------- 3NF
def _latest_first(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r["BookingDate"], r["BookingRef"]), reverse=True)


def resolve(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Make every declared dependency hold: for a conflicting value, the most recent booking wins.

    Returns (resolved rows, list of decisions). The decisions are the point: a human should read them.
    """
    resolved = [dict(r) for r in rows]
    decisions = []
    for lhs, rhs_cols in DESIGN_FDS:
        for rhs in rhs_cols:
            for key, values in fd_violations(resolved, lhs, rhs).items():
                group = [r for r in resolved if tuple(r[c] for c in lhs) == key]
                winner = _latest_first(group)[0][rhs]
                decisions.append({"lhs": lhs, "key": key, "column": rhs, "values": values, "kept": winner,
                                  "rows_changed": sum(r[rhs] != winner for r in group)})
                for r in group:
                    r[rhs] = winner
    return resolved, decisions


def normalize(rows_1nf: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Split the 1NF rows into 3NF tables. Surrogate ids are assigned in name/email order (deterministic)."""
    rows, decisions = resolve(rows_1nf)

    company_names = sorted({r["Company"] for r in rows})
    company_id = {name: i for i, name in enumerate(company_names, start=1)}
    city = {r["Company"]: r["CompanyCity"] for r in rows}
    companies = [{"CompanyId": company_id[n], "CompanyName": n, "City": city[n]} for n in company_names]

    emails = sorted({r["CustomerEmail"] for r in rows})
    customer_id = {e: i for i, e in enumerate(emails, start=1)}
    by_email = {r["CustomerEmail"]: r for r in rows}
    customers = [{"CustomerId": customer_id[e], "Email": e, "FullName": by_email[e]["CustomerName"],
                  "CompanyId": company_id[by_email[e]["Company"]]} for e in emails]

    by_code = {r["CourseCode"]: r for r in rows}
    courses = [{"CourseCode": c, "Title": by_code[c]["CourseTitle"], "ListPrice": by_code[c]["ListPrice"]}
               for c in sorted(by_code)]

    by_ref = {r["BookingRef"]: r for r in rows}
    bookings = [{"BookingRef": b, "BookingDate": by_ref[b]["BookingDate"],
                 "CustomerId": customer_id[by_ref[b]["CustomerEmail"]]} for b in sorted(by_ref)]

    lines = [{"BookingRef": r["BookingRef"], "CourseCode": r["CourseCode"], "PricePaid": r["PricePaid"]}
             for r in sorted(rows, key=lambda r: (r["BookingRef"], r["CourseCode"]))]

    tables = {"Company": companies, "Customer": customers, "Course": courses,
              "Booking": bookings, "BookingLine": lines}
    return tables, decisions


def rebuild(tables: dict[str, list[dict]]) -> list[dict]:
    """The join the view Training.vBookingLines does, in Python."""
    company = {c["CompanyId"]: c for c in tables["Company"]}
    customer = {c["CustomerId"]: c for c in tables["Customer"]}
    course = {c["CourseCode"]: c for c in tables["Course"]}
    booking = {b["BookingRef"]: b for b in tables["Booking"]}
    out = []
    for line in tables["BookingLine"]:
        b = booking[line["BookingRef"]]
        cu = customer[b["CustomerId"]]
        co = company[cu["CompanyId"]]
        c = course[line["CourseCode"]]
        out.append({"BookingRef": b["BookingRef"], "BookingDate": b["BookingDate"], "CustomerEmail": cu["Email"],
                    "CustomerName": cu["FullName"], "Company": co["CompanyName"], "CompanyCity": co["City"],
                    "CourseCode": c["CourseCode"], "CourseTitle": c["Title"], "ListPrice": c["ListPrice"],
                    "PricePaid": line["PricePaid"]})
    return sorted(out, key=lambda r: (r["BookingRef"], r["CourseCode"]))


# ---------------------------------------------------------------- output
COLUMN_ORDER = {
    "Company": ["CompanyId", "CompanyName", "City"],
    "Customer": ["CustomerId", "Email", "FullName", "CompanyId"],
    "Course": ["CourseCode", "Title", "ListPrice"],
    "Booking": ["BookingRef", "BookingDate", "CustomerId"],
    "BookingLine": ["BookingRef", "CourseCode", "PricePaid"],
}
IDENTITY_TABLES = {"Company", "Customer"}


def _literal(value) -> str:
    if isinstance(value, (int, Decimal)):
        return str(value)
    text = str(value).replace("'", "''")
    if len(text) == 10 and text[4] == "-" and text[7] == "-" and text.replace("-", "").isdigit():
        return f"'{text}'"            # ISO date
    return f"N'{text}'"


def to_tsql(tables: dict[str, list[dict]]) -> str:
    """The data script for SQL Server. IDENTITY_INSERT keeps the ids the tests know about."""
    out = ["-- 02-data.sql - GENERATED by src/normalize.py --write-sql from data/bookings_flat.csv. Don't edit.",
           "-- Parents before children, so every foreign key is satisfied as rows arrive.", ""]
    for table, cols in COLUMN_ORDER.items():
        rows = tables[table]
        if table in IDENTITY_TABLES:
            out.append(f"SET IDENTITY_INSERT Training.{table} ON;")
        out.append(f"INSERT INTO Training.{table} ({', '.join(cols)}) VALUES")
        values = [f"    ({', '.join(_literal(r[c]) for c in cols)})" for r in rows]
        out.append(",\n".join(values) + ";")
        if table in IDENTITY_TABLES:
            out.append(f"SET IDENTITY_INSERT Training.{table} OFF;")
        out.append("GO")
        out.append("")
    return "\n".join(out)


def write_csvs(tables: dict[str, list[dict]], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for table, cols in COLUMN_ORDER.items():
        with (folder / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(tables[table])


def report(flat: list[dict]) -> str:
    rows = to_1nf(flat)
    lines = [f"flat export: {len(flat)} rows, {len(flat[0])} columns, repeating group in "
             f"{', '.join(LIST_COLUMNS)}",
             f"1NF: {len(rows)} booking lines"]
    keys = candidate_keys(rows, ONE_NF_COLUMNS)
    key = ("BookingRef", "CourseCode")
    lines.append(f"{len(keys)} column pairs are unique in this sample; the business key is ({', '.join(key)}). "
                 "Data can suggest a key, it can't prove one.")
    lines.append("")
    lines.append("declared dependencies (lhs -> rhs)                         kind                    data")
    for c in check_design(rows):
        dep = f"{', '.join(c['lhs'])} -> {c['rhs']}"
        status = "holds" if c["holds"] else f"CONFLICT {list(c['conflicts'].values())}"
        lines.append(f"  {dep:<56} {classify(c['lhs'], key):<23} {status}")
    tables, decisions = normalize(rows)
    lines.append("")
    for d in decisions:
        lines.append(f"decision: {d['column']} for {', '.join(map(str, d['key']))}: {d['values']} -> kept "
                     f"'{d['kept']}' (latest booking), {d['rows_changed']} row(s) changed")
    lines.append("")
    lines.append("3NF tables: " + ", ".join(f"{t} {len(v)}" for t, v in tables.items()))
    lossless = rebuild(tables) == sorted(resolve(rows)[0], key=lambda r: (r["BookingRef"], r["CourseCode"]))
    lines.append(f"lossless join (rebuild == resolved 1NF): {lossless}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize the flat bookings export.")
    ap.add_argument("csv", nargs="?", type=Path, default=FLAT_CSV)
    ap.add_argument("--write-sql", type=Path, metavar="FILE")
    ap.add_argument("--write-csv", type=Path, metavar="DIR")
    a = ap.parse_args(argv)
    flat = read_flat(a.csv)
    print(report(flat))
    tables, _ = normalize(to_1nf(flat))
    if a.write_sql:
        a.write_sql.write_text(to_tsql(tables), encoding="utf-8")
        print(f"wrote {a.write_sql}")
    if a.write_csv:
        write_csvs(tables, a.write_csv)
        print(f"wrote {len(tables)} CSV files to {a.write_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
