"""Run the episode's T-SQL files and compare the results with expected/*.csv.

Two engines, same files:

* ``sqlserver`` - the real thing. Sends each file to SQL Server 2022 / Azure SQL with the
  mssql-python driver (``pip install mssql-python``), batch by batch (``GO`` separated), unchanged.
* ``duckdb``   - the local check used by the tests and by CI. Each batch is parsed with sqlglot's
  T-SQL dialect (a syntax check) and transpiled to DuckDB, then run in an in-memory database.

    python src/tsql_runner.py                                  # duckdb: setup + every query, check expected/
    python src/tsql_runner.py --show q04                       # print one result as a table
    python src/tsql_runner.py --engine sqlserver --setup       # needs SQL_CONNECTION_STRING
    python src/tsql_runner.py --engine duckdb --write-expected expected

Exit code 0 when every query matches expected/, 1 otherwise.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
SETUP_FILE = "01-schema-and-data.sql"   # 00-create-database.sql is SQL Server only: run it with sqlcmd

_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def split_batches(script: str) -> list[str]:
    """Split a script on GO lines, like sqlcmd and SSMS do. Empty batches are dropped."""
    return [b.strip() for b in _GO.split(script) if b.strip() and not _only_comments(b)]


def _only_comments(batch: str) -> bool:
    lines = [ln.strip() for ln in batch.splitlines()]
    return all(not ln or ln.startswith("--") for ln in lines)


def query_files() -> list[Path]:
    return sorted(SQL_DIR.glob("q*.sql"))


# ---------------------------------------------------------------- T-SQL -> DuckDB
def transpile(batch: str) -> list[str]:
    """T-SQL batch -> DuckDB statements. Raises on syntax errors and on constructs sqlglot can't map.

    Three adjustments, all about DuckDB rather than about the query:
    * the OPTION (...) query-hint clause (e.g. MAXRECURSION) is dropped: hints change how SQL Server
      runs a query, not what it returns;
    * CROSS APPLY becomes CROSS JOIN LATERAL and OUTER APPLY becomes LEFT JOIN LATERAL ... ON TRUE
      (sqlglot's default rendering of APPLY doesn't parse in DuckDB);
    * a CTE that references itself gets WITH RECURSIVE (T-SQL has no such keyword).
    """
    import sqlglot
    from sqlglot import ErrorLevel, exp

    out = []
    for expr in sqlglot.parse(batch, read="tsql", error_level=ErrorLevel.RAISE):
        if expr is None:
            continue
        if expr.args.get("options"):
            expr.set("options", None)
        for with_ in expr.find_all(exp.With):
            # T-SQL has no RECURSIVE keyword; DuckDB requires it when a CTE references itself.
            for cte in with_.expressions:
                if any(t.name.lower() == cte.alias_or_name.lower() and not t.db
                       for t in cte.this.find_all(exp.Table)):
                    with_.set("recursive", True)
        for join in expr.find_all(exp.Join):
            lateral = join.this
            if isinstance(lateral, exp.Lateral) and lateral.args.get("cross_apply") is not None:
                cross = lateral.args["cross_apply"]          # True: CROSS APPLY, False: OUTER APPLY
                lateral.set("cross_apply", None)
                if cross:
                    join.set("kind", "CROSS")
                else:
                    join.set("side", "LEFT")
                    join.set("on", exp.true())
        sql = expr.sql(dialect="duckdb", unsupported_level=ErrorLevel.RAISE)
        if re.fullmatch(r"(\s*/\*.*?\*/\s*)*", sql, re.DOTALL):
            continue  # a trailing comment after the last semicolon parses as an empty statement
        out.append(sql)
    return out


# ---------------------------------------------------------------- engines
class DuckDBEngine:
    name = "duckdb"

    def __init__(self) -> None:
        import duckdb

        self.con = duckdb.connect(":memory:")

    def execute(self, batch: str):
        cur = None
        for stmt in transpile(batch):
            cur = self.con.execute(stmt)
        return cur

    def close(self) -> None:
        self.con.close()


class SqlServerEngine:
    name = "sqlserver"

    def __init__(self, conn_str: str) -> None:
        from mssql_python import connect  # Microsoft's DB-API 2.0 driver

        self.con = connect(conn_str, autocommit=True)   # DDL batches: no open transaction left behind

    def execute(self, batch: str):
        cur = self.con.cursor()
        cur.execute(batch)
        return cur

    def close(self) -> None:
        self.con.close()


def run_script(engine, path: Path) -> None:
    for batch in split_batches(path.read_text(encoding="utf-8")):
        engine.execute(batch)


def run_query(engine, path: Path) -> tuple[list[str], list[tuple]]:
    cur = None
    for batch in split_batches(path.read_text(encoding="utf-8")):
        cur = engine.execute(batch)
    columns = [d[0] for d in cur.description]
    return columns, [tuple(r) for r in cur.fetchall()]


# ---------------------------------------------------------------- comparing results
def normalize(value) -> str:
    """One text form per value, whichever driver returned it (Decimal vs float, date vs datetime)."""
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


def to_table(columns: list[str], rows: list[tuple]) -> list[list[str]]:
    return [list(columns)] + [[normalize(v) for v in r] for r in rows]


def write_csv(path: Path, table: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(table)


def read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def diff(expected: list[list[str]], actual: list[list[str]]) -> list[str]:
    problems = []
    if expected[0] != actual[0]:
        problems.append(f"columns: expected {expected[0]}, got {actual[0]}")
    if len(expected) != len(actual):
        problems.append(f"rows: expected {len(expected) - 1}, got {len(actual) - 1}")
    for i, (e, a) in enumerate(zip(expected[1:], actual[1:]), start=1):
        if e != a:
            problems.append(f"row {i}: expected {e}, got {a}")
    return problems


def format_table(table: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def make_engine(name: str, conn_str: str | None):
    if name == "duckdb":
        return DuckDBEngine()
    if not conn_str:
        sys.exit("Set SQL_CONNECTION_STRING (or pass --conn) to run against SQL Server.")
    return SqlServerEngine(conn_str)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--conn", default=os.environ.get("SQL_CONNECTION_STRING"),
                    help="SQL Server connection string (default: $SQL_CONNECTION_STRING)")
    ap.add_argument("--setup", action="store_true",
                    help=f"run {SETUP_FILE} first (always done for duckdb, which starts empty)")
    ap.add_argument("--show", metavar="PREFIX", help="print the result of the query files starting with PREFIX")
    ap.add_argument("--write-expected", metavar="DIR", type=Path)
    ap.add_argument("--check", metavar="DIR", type=Path, default=EXPECTED_DIR)
    a = ap.parse_args(argv)

    engine = make_engine(a.engine, a.conn)
    try:
        if a.setup or a.engine == "duckdb":
            run_script(engine, SQL_DIR / SETUP_FILE)
        files = [p for p in query_files() if not a.show or p.name.startswith(a.show)]
        failures = 0
        for path in files:
            table = to_table(*run_query(engine, path))
            if a.show:
                print(f"-- {path.name} ({engine.name})\n{format_table(table)}\n({len(table) - 1} rows)\n")
            if a.write_expected:
                a.write_expected.mkdir(parents=True, exist_ok=True)
                write_csv(a.write_expected / f"{path.stem}.csv", table)
                continue
            expected_file = a.check / f"{path.stem}.csv"
            problems = diff(read_csv(expected_file), table) if expected_file.exists() else ["no expected file"]
            failures += bool(problems)
            status = "OK  " if not problems else "FAIL"
            if not a.show or problems:
                print(f"{status} {path.name:<36} {len(table) - 1:>3} rows")
            for p in problems[:5]:
                print(f"       {p}")
        if not a.write_expected and not a.show:
            print(f"{len(files) - failures}/{len(files)} queries match {a.check.name}/ on {engine.name}")
        return 1 if failures else 0
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
