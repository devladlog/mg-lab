"""Run the demo seed data and the reference queries locally on DuckDB (T-SQL transpiled by sqlglot).

Why: the build machine has no SQL Server (no Docker). This does NOT test SQL Server behaviour; it checks that the seed
data is consistent and that the reference answers in queries/ return what expected/ says. In the demo the same queries
run on the real SQL Server 2022 (CON-SQL01) and on Azure SQL Database, and the recorder compares those result sets with
whatever Copilot generated.

  python src/reference_db.py                  # print every reference query result
  python src/reference_db.py --write-expected # (re)write expected/*.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from decimal import Decimal
from pathlib import Path

import duckdb
import sqlglot

logging.getLogger("sqlglot").setLevel(logging.ERROR)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
QUERIES = sorted((HERE / "queries").glob("q*.sql"))


def split_go(text: str) -> list[str]:
    return [b for b in re.split(r"^[ \t]*GO[ \t]*$", text, flags=re.M | re.I) if b.strip()]


def load_seed(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    con = con or duckdb.connect()
    for batch in split_go((HERE / "sql" / "01-contoso-copilot.sql").read_text(encoding="utf-8")):
        for stmt in sqlglot.parse(batch, read="tsql"):
            if stmt is None:
                continue
            sql = stmt.sql(dialect="duckdb")
            if sql.upper().startswith("DROP"):  # a fresh in-memory database has nothing to drop
                continue
            con.execute(sql)
    return con


def run_query(con, path: Path) -> tuple[list[str], list[tuple]]:
    sql = sqlglot.transpile(path.read_text(encoding="utf-8"), read="tsql", write="duckdb")[0]
    cur = con.execute(sql)
    return [d[0] for d in cur.description], cur.fetchall()


def fmt(v) -> str:
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    return str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-expected", action="store_true")
    args = ap.parse_args(argv)
    con = load_seed()
    for q in QUERIES:
        cols, rows = run_query(con, q)
        print(f"-- {q.name}: {len(rows)} row(s)")
        print("   " + " | ".join(cols))
        for r in rows:
            print("   " + " | ".join(fmt(v) for v in r))
        if args.write_expected:
            out = ROOT / "expected" / (q.stem + ".csv")
            with out.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(cols)
                w.writerows([[fmt(v) for v in r] for r in rows])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
