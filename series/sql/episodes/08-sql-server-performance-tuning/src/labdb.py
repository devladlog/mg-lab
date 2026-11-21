"""Shared plumbing for the DEVLADLOG SQL lab runners: run T-SQL files on SQL Server or, locally, on DuckDB.

* ``SqlServerEngine`` - Microsoft's mssql-python driver; batches go to SQL Server unchanged. ``run_script``
  runs every batch of a file, keeps going after a batch fails (like SSMS does), and returns the last result
  set, the error message of each failed batch and, when asked, the ACTUAL plans (SET STATISTICS XML).
* ``DuckDBEngine``    - each batch is parsed with sqlglot's T-SQL dialect and transpiled to DuckDB, an
  in-process engine (no server, no Docker): good for checking data and query results, nothing else.

Episodes 5 and 6 use the same copy of this file (episodes 3 and 4 have an older one).
"""
from __future__ import annotations

import csv
import datetime as dt
import decimal
import re
from dataclasses import dataclass, field
from pathlib import Path

_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)
SQLSERVER_ONLY_MARK = "-- sqlserver only"


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


def is_sqlserver_only(batch: str) -> bool:
    """A batch that contains the marker comment as a line of its own runs on SQL Server only (the local
    check skips it)."""
    return any(ln.strip().lower() == SQLSERVER_ONLY_MARK for ln in batch.splitlines())


def transpile(batch: str) -> list[str]:
    """T-SQL batch -> DuckDB statements (raises on T-SQL syntax errors or unsupported constructs).

    Four adjustments, about DuckDB and sqlglot rather than about the scripts (episode 1 has the first three):
    * the OPTION (...) query-hint clause is dropped: hints change how SQL Server runs a query, not what
      it returns;
    * CROSS APPLY becomes CROSS JOIN LATERAL, OUTER APPLY becomes LEFT JOIN LATERAL ... ON TRUE;
    * a composite PRIMARY KEY (a, b) is parsed with sort options on each column (a NULLS FIRST, ...)
      that DuckDB rejects, so they are dropped;
    * `GENERATE_SERIES(...) AS s` becomes `... AS s(value)` (episodes 3 and 4 have this one).
    """
    import sqlglot
    from sqlglot import ErrorLevel, exp

    out = []
    for expr in sqlglot.parse(batch, read="tsql", error_level=ErrorLevel.RAISE):
        if expr is None:
            continue
        if expr.args.get("options"):
            expr.set("options", None)
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
        for table in expr.find_all(exp.Table):      # T-SQL's GENERATE_SERIES column is `value`; DuckDB's is `generate_series`
            alias = table.args.get("alias")
            if isinstance(table.this, exp.GenerateSeries) and alias is not None and not alias.columns:
                alias.set("columns", [exp.to_identifier("value")])
        for pk in expr.find_all(exp.PrimaryKey):
            pk.set("expressions", [c.this if isinstance(c, exp.Ordered) else c for c in pk.expressions])
        sql = expr.sql(dialect="duckdb", unsupported_level=ErrorLevel.RAISE)
        if re.fullmatch(r"(\s*/\*.*?\*/\s*)*", sql, re.DOTALL):
            continue   # a comment after the last statement parses as an empty statement
        out.append(sql)
    return out


class DuckDBEngine:
    name = "duckdb"

    def __init__(self, schemas=("Sales",)) -> None:
        import duckdb

        self.con = duckdb.connect(":memory:")
        for s in schemas:   # the T-SQL scripts create schemas in "sqlserver only" batches
            self.con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")

    def execute(self, batch: str):
        cur = None
        for stmt in transpile(batch):
            cur = self.con.execute(stmt)
        return cur

    def run_file(self, path: Path) -> None:
        for batch in split_batches(Path(path).read_text(encoding="utf-8")):
            if not is_sqlserver_only(batch):
                self.execute(batch)

    def query(self, sql: str) -> tuple[list[str], list[tuple]]:
        cur = None
        for batch in split_batches(sql):
            cur = self.execute(batch)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

    def close(self) -> None:
        self.con.close()


@dataclass
class ScriptResult:
    columns: list[str] | None = None
    rows: list[tuple] = field(default_factory=list)
    plans: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)      # one message per failed batch


class SqlServerEngine:
    """Microsoft's mssql-python driver; batches are sent unchanged."""
    name = "sqlserver"

    def __init__(self, conn_str: str | None = None, connection=None) -> None:
        if connection is None:
            from mssql_python import connect

            connection = connect(conn_str, autocommit=True)
        self.con = connection

    def _drain(self, cur, result: ScriptResult) -> None:
        while True:
            if cur.description:
                cols, rows = [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]
                if len(cols) == 1 and rows and is_showplan(rows[0][0]):
                    result.plans.extend(str(r[0]) for r in rows)
                else:
                    result.columns, result.rows = cols, rows
            if not cur.nextset():
                return

    def run_script(self, sql: str, plans: bool = False) -> ScriptResult:
        """Every batch of a script, in order. A failing batch is recorded and the next batch still runs,
        which is what SSMS and sqlcmd do with GO-separated batches."""
        result = ScriptResult()
        setup = self.con.cursor()
        if plans:
            setup.execute("SET STATISTICS XML ON;")
        try:
            for batch in split_batches(sql):
                cur = self.con.cursor()
                try:
                    cur.execute(batch)
                    self._drain(cur, result)
                except Exception as e:  # noqa: BLE001 - a T-SQL error is a result here, not a crash
                    result.errors.append(str(e))
                finally:
                    cur.close()
        finally:
            if plans:
                setup.execute("SET STATISTICS XML OFF;")
            setup.close()
        return result

    def run_file(self, path: Path) -> None:
        """Setup files: every batch must succeed."""
        res = self.run_script(Path(path).read_text(encoding="utf-8"))
        if res.errors:
            raise RuntimeError(f"{Path(path).name}: {res.errors[0]}")

    def close(self) -> None:
        self.con.close()


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
