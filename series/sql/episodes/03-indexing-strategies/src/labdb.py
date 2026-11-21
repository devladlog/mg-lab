"""Shared plumbing for the DEVLADLOG SQL lab runners: run T-SQL files on SQL Server or, locally, on DuckDB.

* ``SqlServerEngine`` - Microsoft's mssql-python driver; batches go to SQL Server unchanged.
  ``query_with_plan`` turns on SET STATISTICS XML and returns the ACTUAL plan next to the rows.
* ``DuckDBEngine``    - each batch is parsed with sqlglot's T-SQL dialect and transpiled to DuckDB, an
  in-process engine (no server, no Docker): good for checking data and results, not plans.

Episodes 3 and 4 use the same copy of this file.
"""
from __future__ import annotations

import csv
import datetime as dt
import decimal
import re
from pathlib import Path

_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def is_showplan(value) -> bool:
    """A result-set value that holds an XML showplan (with or without an XML declaration)."""
    return "<ShowPlanXML" in str(value)[:300]


# ---------------------------------------------------------------- T-SQL
def split_batches(script: str) -> list[str]:
    """Split a script on GO lines, like sqlcmd and SSMS do. Empty and comment-only batches are dropped."""
    out = []
    for b in _GO.split(script):
        if any(ln.strip() and not ln.strip().startswith("--") for ln in b.splitlines()):
            out.append(b.strip())
    return out




def transpile(batch: str) -> list[str]:
    """T-SQL batch -> DuckDB statements (raises on T-SQL syntax errors).

    One adjustment, about DuckDB rather than the script: T-SQL's GENERATE_SERIES returns a column named
    `value`; DuckDB names it `generate_series`, so `GENERATE_SERIES(...) AS s` becomes `... AS s(value)`.
    """
    import sqlglot
    from sqlglot import ErrorLevel, exp

    out = []
    for expr in sqlglot.parse(batch, read="tsql", error_level=ErrorLevel.RAISE):
        if expr is None:
            continue
        for table in expr.find_all(exp.Table):
            alias = table.args.get("alias")
            if isinstance(table.this, exp.GenerateSeries) and alias is not None and not alias.columns:
                alias.set("columns", [exp.to_identifier("value")])
        sql = expr.sql(dialect="duckdb", unsupported_level=ErrorLevel.RAISE)
        if re.fullmatch(r"(\s*/\*.*?\*/\s*)*", sql, re.DOTALL):
            continue   # a comment after the last statement parses as an empty statement
        out.append(sql)
    return out


def tsql_syntax_errors(path: Path) -> list[str]:
    """Parse every batch with sqlglot's T-SQL dialect; return the error messages."""
    import sqlglot
    from sqlglot import ErrorLevel

    errors = []
    for i, batch in enumerate(split_batches(path.read_text(encoding="utf-8")), start=1):
        try:
            sqlglot.parse(batch, read="tsql", error_level=ErrorLevel.RAISE)
        except Exception as e:  # noqa: BLE001 - report every parser error the same way
            errors.append(f"{path.name} batch {i}: {str(e).splitlines()[0]}")
    return errors


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

    def query(self, sql: str) -> tuple[list[str], list[tuple]]:
        cur = None
        for batch in split_batches(sql):
            cur = self.execute(batch)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

    def close(self) -> None:
        self.con.close()


class SqlServerEngine:
    """Microsoft's mssql-python driver; batches are sent unchanged."""
    name = "sqlserver"

    def __init__(self, conn_str: str | None = None, connection=None) -> None:
        if connection is None:
            from mssql_python import connect

            connection = connect(conn_str, autocommit=True)
        self.con = connection

    def execute(self, batch: str):
        cur = self.con.cursor()
        cur.execute(batch)
        return cur

    def _result_sets(self, cur) -> list[tuple[list[str], list[tuple]]]:
        sets = []
        while True:
            if cur.description:
                sets.append(([d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]))
            if not cur.nextset():
                return sets

    def query(self, sql: str) -> tuple[list[str], list[tuple]]:
        cols, rows, _ = self.query_with_plan(sql, plans=False)
        return cols, rows

    def query_with_plan(self, sql: str, plans: bool = True):
        """Run a query file; return (columns, rows, [showplan XML]). The plan is the ACTUAL plan."""
        cur = self.con.cursor()
        if plans:
            cur.execute("SET STATISTICS XML ON;")
        try:
            data, xml = None, []
            for batch in split_batches(sql):
                cur.execute(batch)
                for cols, rows in self._result_sets(cur):
                    if len(cols) == 1 and rows and is_showplan(rows[0][0]):
                        xml.extend(str(r[0]) for r in rows)
                    else:
                        data = (cols, rows)
        finally:
            if plans:
                cur.execute("SET STATISTICS XML OFF;")
        if data is None:
            raise RuntimeError("the query returned no result set")
        return data[0], data[1], xml

    def run_batch(self, batch: str) -> None:
        """One batch whose output we don't need (DDL, data load, EXEC of a system procedure)."""
        cur = self.execute(batch)
        while cur.nextset():   # drain row counts and messages
            pass

    def run_file(self, path: Path) -> None:
        for batch in split_batches(Path(path).read_text(encoding="utf-8")):
            self.run_batch(batch)

    def close(self) -> None:
        self.con.close()


def run_script(engine, path: Path) -> None:
    for batch in split_batches(path.read_text(encoding="utf-8")):
        engine.execute(batch)


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




def format_table(table: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)
