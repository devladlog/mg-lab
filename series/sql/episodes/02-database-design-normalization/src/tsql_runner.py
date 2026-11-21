"""Create the 3NF schema, load it, run the queries and the constraint checks, compare with expected/.

Two engines, same .sql files:

* ``sqlserver`` - SQL Server 2022 / Azure SQL through Microsoft's mssql-python driver, files sent unchanged.
* ``duckdb``   - local check for tests and CI: each batch is parsed with sqlglot's T-SQL dialect and
  transpiled to DuckDB (in memory). No server, no Docker.

    python src/tsql_runner.py                                 # duckdb: setup, queries vs expected/, constraints
    python src/tsql_runner.py --show q02                      # print a result as a table
    python src/tsql_runner.py --engine sqlserver --setup      # needs SQL_CONNECTION_STRING (Database=ContosoTraining)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import logging
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
SETUP_FILES = ["01-schema.sql", "02-data.sql"]      # 00-create-database.sql: SQL Server only, run it against master
SHOULD_FAIL_FILE = "04-should-fail.sql"
COUNT_TABLES = ["Company", "Customer", "Course", "Booking", "BookingLine"]

_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)
logging.getLogger("sqlglot").setLevel(logging.ERROR)   # SET IDENTITY_INSERT is parsed as a generic command


def split_batches(script: str) -> list[str]:
    """Split on GO lines like sqlcmd/SSMS; drop empty and comment-only batches."""
    out = []
    for b in _GO.split(script):
        lines = [ln.strip() for ln in b.splitlines()]
        if any(ln and not ln.startswith("--") for ln in lines):
            out.append(b.strip())
    return out


def query_files() -> list[Path]:
    return sorted(SQL_DIR.glob("q*.sql"))


# ---------------------------------------------------------------- T-SQL -> DuckDB
def transpile(batch: str) -> list[str]:
    return [sql for sql, _ in transpile_with_kinds(batch)]


def transpile_with_kinds(batch: str) -> list[tuple[str, bool]]:
    """T-SQL batch -> DuckDB statements. Raises on syntax errors and on constructs sqlglot can't map.

    Adjustments, all about DuckDB rather than about the design:
    * ``SET IDENTITY_INSERT`` is skipped (DuckDB has no such session option; the ids are inserted anyway);
    * ``IDENTITY(1,1)`` becomes a DEFAULT from a sequence that starts at 1000 (DuckDB has no identity columns);
    * index and key column lists lose the NULLS FIRST sqlglot adds to mimic SQL Server's sort order
      (DuckDB doesn't accept it there).
    """
    import sqlglot
    from sqlglot import ErrorLevel, exp

    out = []
    for expr in sqlglot.parse(batch, read="tsql", error_level=ErrorLevel.RAISE):
        if expr is None:
            continue
        if isinstance(expr, (exp.Command, exp.Set)) and "IDENTITY_INSERT" in expr.sql(dialect="tsql").upper():
            continue
        if isinstance(expr, exp.Create) and expr.kind == "TABLE":
            table = expr.this.this if isinstance(expr.this, exp.Schema) else expr.this
            for col in expr.find_all(exp.ColumnDef):
                for cc in list(col.args.get("constraints") or []):
                    if isinstance(cc.kind, exp.GeneratedAsIdentityColumnConstraint):
                        seq = f"seq_{table.db}_{table.name}_{col.name}"
                        out.append((f"CREATE OR REPLACE SEQUENCE {seq} START 1000", False))
                        cc.set("kind", exp.DefaultColumnConstraint(this=exp.func("nextval", exp.Literal.string(seq))))
        if isinstance(expr, exp.Create) and expr.kind in ("TABLE", "INDEX"):
            for ordered in expr.find_all(exp.Ordered):
                ordered.set("nulls_first", False)
        sql = expr.sql(dialect="duckdb", unsupported_level=ErrorLevel.RAISE)
        if re.fullmatch(r"(\s*/\*.*?\*/\s*)*", sql, re.DOTALL):
            continue
        out.append((sql, isinstance(expr, exp.Query)))   # True when the statement returns rows
    return out


# ---------------------------------------------------------------- engines
class DuckDBEngine:
    name = "duckdb"

    def __init__(self) -> None:
        import duckdb

        self.con = duckdb.connect(":memory:")

    def run(self, batch: str):
        """Execute a batch; return (columns, rows) of the last statement that produced a result, else None."""
        result = None
        for stmt, returns_rows in transpile_with_kinds(batch):
            cur = self.con.execute(stmt)
            if returns_rows:
                result = ([d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()])
        return result

    def close(self) -> None:
        self.con.close()


class SqlServerEngine:
    name = "sqlserver"

    def __init__(self, conn_str: str) -> None:
        from mssql_python import connect  # Microsoft's DB-API 2.0 driver

        self.con = connect(conn_str, autocommit=True)

    def run(self, batch: str):
        cur = self.con.cursor()
        cur.execute(batch)
        result = None
        while True:
            if cur.description:
                result = ([d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()])
            if not cur.nextset():
                break
        return result

    def close(self) -> None:
        self.con.close()


def run_script(engine, path: Path) -> None:
    for batch in split_batches(path.read_text(encoding="utf-8")):
        engine.run(batch)


def setup(engine) -> None:
    for name in SETUP_FILES:
        run_script(engine, SQL_DIR / name)


def run_query(engine, path: Path):
    result = None
    for batch in split_batches(path.read_text(encoding="utf-8")):
        result = engine.run(batch) or result
    return result


def row_counts(engine) -> dict[str, int]:
    return {t: engine.run(f"SELECT COUNT(*) AS n FROM Training.{t};")[1][0][0] for t in COUNT_TABLES}


def check_constraints(engine) -> list[tuple[str, bool, str]]:
    """Run every batch of 04-should-fail.sql. Each must raise; the row counts must not move."""
    before = row_counts(engine)
    results = []
    for batch in split_batches((SQL_DIR / SHOULD_FAIL_FILE).read_text(encoding="utf-8")):
        title = next((ln.strip("- ").strip() for ln in batch.splitlines() if re.match(r"--\s*\d+\.", ln)),
                     batch.splitlines()[0])
        try:
            engine.run(batch)
            results.append((title, False, "accepted!"))
        except Exception as e:  # noqa: BLE001 - any engine's constraint error
            msg = " ".join(str(e).split())
            results.append((title, True, msg[:150]))
    if row_counts(engine) != before:
        results.append(("row counts unchanged", False, f"{before} -> {row_counts(engine)}"))
    return results


# ---------------------------------------------------------------- comparing results
def normalize(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, decimal.Decimal)):
        return f"{decimal.Decimal(str(value)).quantize(decimal.Decimal('0.01'), decimal.ROUND_HALF_UP)}"
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time(0) else value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def to_table(columns, rows) -> list[list[str]]:
    return [list(columns)] + [[normalize(v) for v in r] for r in rows]


def write_csv(path: Path, table) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(table)


def read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def diff(expected, actual) -> list[str]:
    problems = []
    if expected[0] != actual[0]:
        problems.append(f"columns: expected {expected[0]}, got {actual[0]}")
    if len(expected) != len(actual):
        problems.append(f"rows: expected {len(expected) - 1}, got {len(actual) - 1}")
    for i, (e, a) in enumerate(zip(expected[1:], actual[1:]), start=1):
        if e != a:
            problems.append(f"row {i}: expected {e}, got {a}")
    return problems


def format_table(table) -> str:
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--conn", default=os.environ.get("SQL_CONNECTION_STRING"))
    ap.add_argument("--setup", action="store_true", help="create and load the schema (always done for duckdb)")
    ap.add_argument("--show", metavar="PREFIX")
    ap.add_argument("--write-expected", metavar="DIR", type=Path)
    ap.add_argument("--check", metavar="DIR", type=Path, default=EXPECTED_DIR)
    ap.add_argument("--no-constraints", action="store_true", help="skip the 04-should-fail.sql checks")
    a = ap.parse_args(argv)

    if a.engine == "sqlserver" and not a.conn:
        sys.exit("Set SQL_CONNECTION_STRING (or pass --conn) to run against SQL Server.")
    engine = DuckDBEngine() if a.engine == "duckdb" else SqlServerEngine(a.conn)
    try:
        if a.setup or a.engine == "duckdb":
            setup(engine)
            print("loaded: " + ", ".join(f"{t} {n}" for t, n in row_counts(engine).items()))
        failures = 0
        files = [p for p in query_files() if not a.show or p.name.startswith(a.show)]
        for path in files:
            table = to_table(*run_query(engine, path))
            if a.show:
                print(f"-- {path.name} ({engine.name})\n{format_table(table)}\n({len(table) - 1} rows)\n")
                continue
            if a.write_expected:
                a.write_expected.mkdir(parents=True, exist_ok=True)
                write_csv(a.write_expected / f"{path.stem}.csv", table)
                continue
            exp_file = a.check / f"{path.stem}.csv"
            problems = diff(read_csv(exp_file), table) if exp_file.exists() else ["no expected file"]
            failures += bool(problems)
            print(f"{'OK  ' if not problems else 'FAIL'} {path.name:<28} {len(table) - 1:>3} rows")
            for p in problems[:5]:
                print(f"       {p}")
        if not a.show and not a.write_expected:
            print(f"{len(files) - failures}/{len(files)} queries match {a.check.name}/ on {engine.name}")
            if not a.no_constraints:
                results = check_constraints(engine)
                for title, ok, msg in results:
                    print(f"{'REJECTED' if ok else 'FAIL    '} {title}\n         {msg}")
                bad = sum(not ok for _, ok, _ in results)
                print(f"{len(results) - bad}/{len(results)} constraint checks behaved on {engine.name}")
                failures += bad
        return 1 if failures else 0
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
