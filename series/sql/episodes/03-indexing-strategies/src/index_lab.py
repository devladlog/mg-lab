"""Indexing lab runner: same T-SQL files, two engines.

* ``sqlserver`` - the demo. For every scenario step it drops the lab indexes, creates the step's index,
  runs the query with SET STATISTICS XML ON and reads the actual plan: which operators ran, on which
  index, how many pages were read, how big the index is. Each step has checks ("Index Seek on
  IX_Orders_CustomerId", "fewer pages than: no index") and the run fails if SQL Server disagrees.
  Results are compared with expected/ in every step: an index must never change the answer.
* ``duckdb``    - the local check (tests, CI, no server). Loads the same generated data, runs the three
  queries and compares them with expected/; every .sql file is parsed with sqlglot's T-SQL dialect.
  DuckDB has no SQL Server plans, so the index steps only run on SQL Server.

    python src/index_lab.py                                   # duckdb: data + queries + syntax
    python src/index_lab.py --engine sqlserver --setup        # needs SQL_CONNECTION_STRING
    python src/index_lab.py --engine sqlserver --scenario customer-orders --save-plans plans
    python src/index_lab.py --write-expected expected         # regenerate expected/ (duckdb)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import showplan  # noqa: E402
from labdb import (DuckDBEngine, SqlServerEngine, diff, format_table, read_csv, run_script,  # noqa: E402
                   to_table, tsql_syntax_errors, write_csv)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
SETUP_FILE = "01-schema-and-data.sql"
SQLSERVER_ONLY = {"00-create-database.sql"}       # CREATE/ALTER DATABASE: nothing to check locally
DROP_FILE = "ix00-drop-lab-indexes.sql"

_CREATE_INDEX = re.compile(r"CREATE\s+(?:UNIQUE\s+)?(?:NONCLUSTERED\s+|CLUSTERED\s+)?(?:COLUMNSTORE\s+)?"
                           r"INDEX\s+(\w+)", re.IGNORECASE)


# ---------------------------------------------------------------- scenarios
@dataclass
class Step:
    name: str
    ddl: str | None                    # ix file to run after ix00, or None for "no index"
    checks: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    key: str
    query: str
    steps: list[Step]


SCENARIOS = [
    Scenario("customer-orders", "q01-customer-orders.sql", [
        Step("no index", None, [
            "has: Clustered Index Scan @ PK_Orders"]),
        Step("narrow index", "ix01-customer.sql", [
            "has: Index Seek @ IX_Orders_CustomerId",
            "has: Key Lookup @ PK_Orders",
            "fewer pages than: no index"]),
        Step("covering, wrong key order", "ix02-date-customer-covering.sql", [
            "has: Index Scan @ IX_Orders_OrderDate_CustomerId",
            "not: Index Seek",
            "not: Key Lookup",
            "fewer pages than: no index",
            "more pages than: narrow index"]),
        Step("covering, right key order", "ix03-customer-date-covering.sql", [
            "has: Index Seek @ IX_Orders_CustomerId_OrderDate",
            "not: Key Lookup",
            "not: Sort",
            "fewer pages than: narrow index"]),
    ]),
    Scenario("open-orders", "q02-open-orders.sql", [
        Step("no index", None, [
            "has: Clustered Index Scan @ PK_Orders"]),
        Step("full-table index", "ix04-status-date.sql", [
            "has: Index Seek @ IX_Orders_Status_OrderDate",
            "fewer pages than: no index"]),
        Step("filtered index", "ix05-open-orders-filtered.sql", [
            "has: Index Seek @ IX_Orders_Open",
            "fewer pages than: no index",
            "index pages below 10% of: full-table index"]),
    ]),
    Scenario("revenue-report", "q03-revenue-by-year-channel.sql", [
        Step("no index", None, [
            "has: Clustered Index Scan @ PK_Orders"]),
        Step("columnstore", "ix06-columnstore.sql", [
            "has: Columnstore Index Scan @ NCCI_Orders_Reporting",
            "batch: Columnstore Index Scan",
            "fewer pages than: no index"]),
    ]),
]
FINAL_DESIGN = ["ix03-customer-date-covering.sql", "ix05-open-orders-filtered.sql", "ix06-columnstore.sql"]


@dataclass
class StepResult:
    step: Step
    plan: showplan.StatementPlan
    index_pages: int | None
    result_problems: list[str]
    failures: list[str] = field(default_factory=list)


CHECK_KINDS = {"has", "not", "batch", "fewer pages than", "more pages than"}




def evaluate(check: str, result: StepResult, earlier: dict[str, StepResult]) -> str | None:
    """None if the check holds, else a message. Checks are plain strings so they read like the README."""
    kind, _, arg = (s.strip() for s in check.partition(":"))
    if kind not in CHECK_KINDS and not kind.startswith("index pages below"):
        raise ValueError(f"unknown check: {check}")
    plan = result.plan
    if kind in ("has", "not", "batch"):
        op, _, index = (s.strip() for s in arg.partition("@"))
        found = plan.find(op, index or None)
        if kind == "has" and not found:
            return f"expected {arg}, plan is {plan.access_summary()}"
        if kind == "not" and found:
            return f"did not expect {op}, plan is {plan.access_summary()}"
        if kind == "batch" and not any(o.execution_mode == "Batch" for o in found):
            return f"expected {op} in batch mode, got {[o.execution_mode for o in found] or 'no such operator'}"
        return None
    if kind in ("fewer pages than", "more pages than"):
        other = earlier[arg].plan.pages_read
        mine = plan.pages_read
        ok = mine < other if kind.startswith("fewer") else mine > other
        return None if ok else f"{mine} pages read, '{arg}' read {other}: expected {kind.split()[0]}"
    if kind.startswith("index pages below"):
        pct = int(re.search(r"(\d+)%", kind).group(1))
        other = earlier[arg].index_pages
        if result.index_pages is None or other is None:
            return "index size not available"
        return None if result.index_pages * 100 < other * pct else (
            f"index is {result.index_pages} pages, '{arg}' is {other}: expected below {pct}%")
    raise ValueError(f"unknown check: {check}")   # pragma: no cover - kinds are validated above


def created_indexes(sql_file: str) -> list[str]:
    return _CREATE_INDEX.findall((SQL_DIR / sql_file).read_text(encoding="utf-8"))


def check_expected(query_file: str, columns, rows) -> list[str]:
    exp_file = EXPECTED_DIR / (Path(query_file).stem + ".csv")
    if not exp_file.exists():
        return [f"no expected file {exp_file.name}"]
    return diff(read_csv(exp_file), to_table(columns, rows))


# ---------------------------------------------------------------- the two runs
def run_local(engine, write_expected: Path | None = None, out=print) -> int:
    run_script(engine, SQL_DIR / SETUP_FILE)
    counts = {t: engine.query(f"SELECT COUNT(*) AS n FROM Sales.{t};")[1][0][0] for t in ("Customers", "Orders")}
    out(f"setup: Customers {counts['Customers']}, Orders {counts['Orders']} ({engine.name})")
    failures = 0
    queries = [s.query for s in SCENARIOS]
    for q in queries:
        cols, rows = engine.query((SQL_DIR / q).read_text(encoding="utf-8"))
        if write_expected:
            write_expected.mkdir(parents=True, exist_ok=True)
            write_csv(write_expected / (Path(q).stem + ".csv"), to_table(cols, rows))
            out(f"wrote {q[:-4]}.csv ({len(rows)} rows)")
            continue
        problems = check_expected(q, cols, rows)
        failures += bool(problems)
        out(f"{'OK  ' if not problems else 'FAIL'} {q:<36} {len(rows):>3} rows")
        for p in problems[:5]:
            out(f"       {p}")
    if not write_expected:
        out(f"{len(queries) - failures}/{len(queries)} queries match expected/ on {engine.name}")
    files = sorted(SQL_DIR.glob("*.sql"))
    errors = [e for f in files if f.name not in SQLSERVER_ONLY for e in tsql_syntax_errors(f)]
    for e in errors:
        out(f"SYNTAX {e}")
    out(f"syntax: {len(files) - len(SQLSERVER_ONLY) - len({e.split()[0] for e in errors})}"
        f"/{len(files) - len(SQLSERVER_ONLY)} T-SQL files parse (sqlglot, tsql dialect)")
    out("plans : SQL Server only - run with --engine sqlserver for the index steps")
    return 1 if failures or errors else 0


def index_pages(engine: SqlServerEngine, names: list[str]) -> int | None:
    if not names:
        return None
    cols, rows = engine.query((SQL_DIR / "dmv-index-sizes.sql").read_text(encoding="utf-8"))
    by_name = {r[cols.index("IndexName")]: int(r[cols.index("UsedPages")]) for r in rows}
    return sum(by_name.get(n, 0) for n in names)


def run_scenario(engine: SqlServerEngine, sc: Scenario, save_plans: Path | None = None,
                 out=print) -> list[StepResult]:
    sql = (SQL_DIR / sc.query).read_text(encoding="utf-8")
    out(f"\n== {sc.key}  ({sc.query})")
    results: dict[str, StepResult] = {}
    table = [["step", "plan", "pages read", "index pages", "check"]]
    for n, step in enumerate(sc.steps, start=1):
        engine.run_file(SQL_DIR / DROP_FILE)
        if step.ddl:
            engine.run_file(SQL_DIR / step.ddl)
        cols, rows, xml = engine.query_with_plan(sql)
        plans = [p for doc in xml for p in showplan.parse_showplan(doc)]
        if not plans:
            raise RuntimeError(f"{sc.key}/{step.name}: SQL Server returned no plan")
        if save_plans:
            save_plans.mkdir(parents=True, exist_ok=True)
            # UTF-8 without an XML declaration: SSMS and showplan.py open it (File > Open > *.sqlplan)
            (save_plans / f"{sc.key}-{n}.sqlplan").write_text(
                re.sub(r"^\s*<\?xml[^>]*\?>", "", xml[0]), encoding="utf-8")
        res = StepResult(step, plans[-1], index_pages(engine, created_indexes(step.ddl) if step.ddl else []),
                         check_expected(sc.query, cols, rows))
        res.failures = [m for c in step.checks if (m := evaluate(c, res, results))] + res.result_problems
        results[step.name] = res
        table.append([f"{n} {step.name}", res.plan.access_summary(), str(res.plan.pages_read),
                      "-" if res.index_pages is None else str(res.index_pages),
                      "OK" if not res.failures else "FAIL"])
    out(format_table(table))
    for res in results.values():
        for f in res.failures:
            out(f"   FAIL {res.step.name}: {f}")
    first = next(iter(results.values())).plan
    for mi in first.missing_indexes:
        out(f"   optimizer's missing index request (step 1, impact {mi.impact:.1f}%):\n"
            f"     {mi.to_create_index()}")
    if not first.missing_indexes:
        # Learn: "Suggestions aren't made for trivial query plans."
        out(f"   optimizer's missing index request (step 1): none "
            f"(optimization level {first.optimization_level or 'unknown'})")
    ok_rows = all(not r.result_problems for r in results.values())
    out(f"   results: {len(rows)} rows, {'identical to expected/ in every step' if ok_rows else 'MISMATCH'}")
    return list(results.values())


def run_final(engine: SqlServerEngine, out=print) -> None:
    """Create the final design, run each query once, show sizes and usage."""
    engine.run_file(SQL_DIR / DROP_FILE)
    for f in FINAL_DESIGN:
        engine.run_file(SQL_DIR / f)
    for sc in SCENARIOS:
        engine.query((SQL_DIR / sc.query).read_text(encoding="utf-8"))
    for f in ("dmv-index-sizes.sql", "dmv-index-usage.sql"):
        cols, rows = engine.query((SQL_DIR / f).read_text(encoding="utf-8"))
        out(f"\n-- {f}\n{format_table(to_table(cols, rows))}")


def run_sqlserver(engine: SqlServerEngine, setup: bool, only: str | None, save_plans: Path | None,
                  final: bool, out=print) -> int:
    if setup:
        engine.run_file(SQL_DIR / SETUP_FILE)
        out("setup: Sales.Customers and Sales.Orders loaded")
    failed = 0
    for sc in SCENARIOS:
        if only and sc.key != only:
            continue
        failed += sum(bool(r.failures) for r in run_scenario(engine, sc, save_plans, out))
    if final and not only:
        run_final(engine, out)
    total = sum(len(sc.steps) for sc in SCENARIOS if not only or sc.key == only)
    out(f"\n{total - failed}/{total} steps behaved as expected on {engine.name}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--conn", default=os.environ.get("SQL_CONNECTION_STRING"),
                    help="SQL Server connection string (default: $SQL_CONNECTION_STRING)")
    ap.add_argument("--setup", action="store_true", help=f"sqlserver: run {SETUP_FILE} first")
    ap.add_argument("--scenario", choices=[s.key for s in SCENARIOS])
    ap.add_argument("--save-plans", metavar="DIR", type=Path, help="sqlserver: write each actual plan as .sqlplan")
    ap.add_argument("--no-final", action="store_true", help="sqlserver: skip the final design + DMV report")
    ap.add_argument("--write-expected", metavar="DIR", type=Path, help="duckdb: regenerate expected/")
    a = ap.parse_args(argv)

    if a.engine == "duckdb":
        engine = DuckDBEngine()
        try:
            return run_local(engine, a.write_expected)
        finally:
            engine.close()
    if not a.conn:
        sys.exit("Set SQL_CONNECTION_STRING (or pass --conn) to run against SQL Server.")
    engine = SqlServerEngine(a.conn)
    try:
        return run_sqlserver(engine, a.setup, a.scenario, a.save_plans, not a.no_final)
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
