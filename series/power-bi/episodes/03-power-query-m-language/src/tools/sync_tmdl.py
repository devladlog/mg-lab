#!/usr/bin/env python3
"""Copy the Power Query queries (src/queries/*.pq) into the semantic model (TMDL), so the .pq files are
the single source of truth and the model can never drift from what pq-lint and the tests checked.

  * ExportFolder, fnReadExport, fnDimension, SalesExport -> definition/expressions.tmdl
    (shared expressions = queries that Power BI does not load into the model)
  * Product, Customer, Store, Date, Sales                 -> the M partition at the end of tables/<name>.tmdl

Usage:
    python sync_tmdl.py           # rewrite the TMDL files
    python sync_tmdl.py --check   # exit 1 if a TMDL file is out of date (used by the tests)
"""
import argparse
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
QUERIES = SRC / "queries"
DEFINITION = SRC / "ContosoSales.SemanticModel" / "definition"

SHARED = {
    "ExportFolder": "Folder that receives the monthly ERP exports (sales_yyyy-MM.csv). Keep the trailing backslash.",
    "fnReadExport": "Function: reads one monthly ERP export (semicolons, decimal comma, dd/MM/yyyy) into a typed table.",
    "fnDimension": "Function: distinct members of a business key with a surrogate key starting at 1.",
    "SalesExport": "Staging query, not loaded: all monthly exports combined, the newest copy of each order line kept.",
}
LOADED = ["Product", "Customer", "Store", "Date", "Sales"]


def read_query(name: str) -> str:
    return (QUERIES / f"{name}.pq").read_text(encoding="utf-8").strip("\n")


def indent(text: str, tabs: int) -> str:
    pad = "\t" * tabs
    return "\n".join(pad + line if line.strip() else "" for line in text.split("\n"))


def render_expressions() -> str:
    blocks = []
    for name, description in SHARED.items():
        m = read_query(name)
        if "\n" not in m:
            blocks.append(f"/// {description}\nexpression {name} = {m}\n")
        else:
            blocks.append(f"/// {description}\nexpression {name} =\n{indent(m, 2)}\n")
    return "\n".join(blocks)


def render_partition(table: str) -> str:
    return (f"\tpartition {table} = m\n"
            f"\t\tmode: import\n"
            f"\t\tsource =\n"
            f"{indent(read_query(table), 4)}\n")


def render_table(table: str, current: str) -> str:
    head = re.split(r"^\tpartition ", current, maxsplit=1, flags=re.M)[0]
    return head + render_partition(table)


def targets():
    out = {DEFINITION / "expressions.tmdl": render_expressions()}
    for t in LOADED:
        path = DEFINITION / "tables" / f"{t}.tmdl"
        out[path] = render_table(t, path.read_text(encoding="utf-8"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    stale = []
    for path, text in targets().items():
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        if old != text:
            stale.append(path.relative_to(SRC))
            if not a.check:
                path.write_text(text, encoding="utf-8")
    if a.check:
        for p in stale:
            print(f"out of date: {p}")
        print("TMDL in sync with queries" if not stale else f"{len(stale)} file(s) out of date")
        sys.exit(1 if stale else 0)
    print(f"updated {len(stale)} file(s)" if stale else "already in sync")


if __name__ == "__main__":
    main()
