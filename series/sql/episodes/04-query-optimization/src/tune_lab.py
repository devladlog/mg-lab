"""Query optimization lab runner: same T-SQL files, two engines.

* ``sqlserver`` - the demo. Runs each query or procedure call with SET STATISTICS XML ON, reads the
  actual plan (operators, pages read, warnings, compiled vs runtime parameter values) and checks it:
  "Index Seek on IX_Orders_OrderDate", "warning: PlanAffectingConvert", "compiled: 4242". Then it uses
  Query Store to list the plans the procedure has had and forces one. Results are checked every time.
* ``duckdb``    - the local check (tests, CI, no server): loads the same generated data, proves each
  rewrite returns exactly what the original returns, and computes expected/.

    python src/tune_lab.py                                    # duckdb: data, rewrites, procedure query
    python src/tune_lab.py --engine sqlserver --setup         # needs SQL_CONNECTION_STRING
    python src/tune_lab.py --engine sqlserver --scenario sniffing --save-plans plans
    python src/tune_lab.py --write-expected expected          # regenerate expected/ (duckdb)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import showplan  # noqa: E402
from labdb import (DuckDBEngine, SqlServerEngine, diff, format_table, normalize, read_csv,  # noqa: E402
                   run_script, to_table, tsql_syntax_errors, write_csv)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
SETUP_FILE = "01-schema-and-data.sql"
INDEX_FILE = "02-indexes.sql"
PROC_FILE = "03-procedures.sql"
# Files sqlglot can't meaningfully check (database options, procedure bodies): SQL Server only.
SQLSERVER_ONLY = {"00-create-database.sql", PROC_FILE, "psp-off.sql", "psp-on.sql"}
RECOMPILE = "EXEC sp_recompile N'Sales.GetCustomerOrders';"
PROC_CUSTOMERS = (1, 4242)           # Contoso Megastore (60,000 orders) and a typical customer (7)


def proc(customer: int, recompile_hint: bool = False) -> str:
    name = "Sales.GetCustomerOrders_Recompile" if recompile_hint else "Sales.GetCustomerOrders"
    return f"EXEC {name} @CustomerId = {customer};"


@dataclass
class Run:
    name: str
    sql: str                                   # a .sql file in src/sql, or inline T-SQL
    before: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    expected: str | None = None                # expected/<stem>.csv, or "proc:<CustomerId>"


@dataclass
class Scenario:
    key: str
    title: str
    runs: list[Run]


SCENARIOS = [
    Scenario("sargable", "a function on the column vs a range on the column", [
        Run("function on column", "q01a-function-on-column.sql", checks=[
            "has: Index Scan @ IX_Orders_OrderDate", "not: Index Seek"], expected="q01a-function-on-column"),
        Run("date range", "q01b-date-range.sql", checks=[
            "has: Index Seek @ IX_Orders_OrderDate", "fewer pages than: function on column"],
            expected="q01b-date-range"),
    ]),
    Scenario("conversion", "comparing a varchar column with an int", [
        Run("int literal", "q02a-implicit-conversion.sql", checks=[
            "not: Index Seek", "warning: PlanAffectingConvert"], expected="q02a-implicit-conversion"),
        Run("varchar literal", "q02b-matching-type.sql", checks=[
            "has: Index Seek @ UX_Customers_AccountNumber", "no warning: PlanAffectingConvert",
            "fewer pages than: int literal"], expected="q02b-matching-type"),
    ]),
    Scenario("sniffing", "one cached plan, two very different customers (PSP optimization off)", [
        Run("Megastore first", proc(1), before=["psp-off.sql", RECOMPILE], checks=[
            "has: Clustered Index Scan @ PK_Orders", "compiled: 1", "runtime: 1"], expected="proc:1"),
        Run("then customer 4242", proc(4242), checks=[
            "has: Clustered Index Scan @ PK_Orders", "compiled: 1", "runtime: 4242"], expected="proc:4242"),
        Run("4242 first", proc(4242), before=[RECOMPILE], checks=[
            "has: Index Seek @ IX_Orders_CustomerId", "has: Key Lookup", "compiled: 4242",
            "fewer pages than: then customer 4242"], expected="proc:4242"),
        Run("then Megastore", proc(1), checks=[
            "has: Key Lookup", "compiled: 4242", "runtime: 1", "more pages than: Megastore first"],
            expected="proc:1"),
        Run("RECOMPILE, 4242", proc(4242, True), checks=[
            "has: Index Seek @ IX_Orders_CustomerId"], expected="proc:4242"),
        Run("RECOMPILE, Megastore", proc(1, True), checks=[
            "has: Clustered Index Scan @ PK_Orders", "fewer pages than: then Megastore"], expected="proc:1"),
    ]),
    Scenario("query-store", "force the plan that is good enough for both", [
        Run("forced plan, 4242 first", proc(4242), before=[RECOMPILE], checks=[
            "has: Clustered Index Scan @ PK_Orders"], expected="proc:4242"),
        Run("forced plan, Megastore", proc(1), checks=[
            "has: Clustered Index Scan @ PK_Orders"], expected="proc:1"),
    ]),
]
CHECK_KINDS = {"has", "not", "fewer pages than", "more pages than", "warning", "no warning", "compiled", "runtime"}


@dataclass
class RunResult:
    run: Run
    plan: showplan.StatementPlan
    result_problems: list[str]
    rows: int = 0
    failures: list[str] = field(default_factory=list)


def all_warnings(plan: showplan.StatementPlan) -> list[str]:
    return plan.warnings + [w for o in plan.operators for w in o.warnings]


def evaluate(check: str, result: RunResult, earlier: dict[str, RunResult]) -> str | None:
    """None if the check holds, else a message."""
    kind, _, arg = (s.strip() for s in check.partition(":"))
    if kind not in CHECK_KINDS:
        raise ValueError(f"unknown check: {check}")
    plan = result.plan
    if kind in ("has", "not"):
        op, _, index = (s.strip() for s in arg.partition("@"))
        found = plan.find(op, index or None)
        if kind == "has" and not found:
            return f"expected {arg}, plan is {plan.access_summary()}"
        if kind == "not" and found:
            return f"did not expect {op}, plan is {plan.access_summary()}"
        return None
    if kind.endswith("pages than"):
        other, mine = earlier[arg].plan.pages_read, plan.pages_read
        ok = mine < other if kind.startswith("fewer") else mine > other
        return None if ok else f"{mine} pages read, '{arg}' read {other}: expected {kind.split()[0]}"
    if kind in ("warning", "no warning"):
        hits = [w for w in all_warnings(plan) if arg in w]
        if kind == "warning" and not hits:
            return f"expected a {arg} warning, got {all_warnings(plan) or 'none'}"
        if kind == "no warning" and hits:
            return f"did not expect {hits}"
        return None
    # compiled / runtime: the @CustomerId value the plan was compiled for / ran with
    p = next((p for p in plan.parameters if p.name == "@CustomerId"), None)
    value = None if p is None else (p.compiled_value if kind == "compiled" else p.runtime_value)
    return None if value == arg else f"expected {kind} @CustomerId = {arg}, plan says {value}"


# ---------------------------------------------------------------- results
def proc_query(customer: int) -> str:
    """The SELECT inside Sales.GetCustomerOrders with the parameter as a literal (for DuckDB and tests)."""
    text = (SQL_DIR / PROC_FILE).read_text(encoding="utf-8")
    body = re.search(r"SET NOCOUNT ON;\s*(SELECT .*?;)\s*END;", text, re.S).group(1)
    return body.replace("@CustomerId", str(int(customer)))


def proc_summary(customer: int, columns, rows) -> list[list[str]]:
    """What the runner compares for a procedure call: row count, revenue, first and last OrderId."""
    i_id, i_amt = columns.index("OrderId"), columns.index("TotalAmount")
    revenue = sum((Decimal(str(r[i_amt])) for r in rows), Decimal(0))
    return [["CustomerId", "Rows", "Revenue", "FirstOrderId", "LastOrderId"],
            [str(customer), str(len(rows)), normalize(revenue),
             str(rows[0][i_id]) if rows else "NULL", str(rows[-1][i_id]) if rows else "NULL"]]


def check_result(expected: str | None, columns, rows) -> list[str]:
    if expected is None:
        return []
    if expected.startswith("proc:"):
        customer = int(expected[5:])
        want = [r for r in read_csv(EXPECTED_DIR / "proc-customer-orders.csv") if r[0] in ("CustomerId", str(customer))]
        return diff(want, proc_summary(customer, columns, rows))
    return diff(read_csv(EXPECTED_DIR / f"{expected}.csv"), to_table(columns, rows))


def sql_text(sql: str) -> str:
    return (SQL_DIR / sql).read_text(encoding="utf-8") if sql.endswith(".sql") else sql


# ---------------------------------------------------------------- local run (DuckDB)
LOCAL_QUERIES = ["q01a-function-on-column.sql", "q01b-date-range.sql",
                 "q02a-implicit-conversion.sql", "q02b-matching-type.sql"]


def run_local(engine, write_expected: Path | None = None, out=print) -> int:
    run_script(engine, SQL_DIR / SETUP_FILE)
    out(f"setup: Orders {engine.query('SELECT COUNT(*) FROM Sales.Orders;')[1][0][0]} ({engine.name})")
    failures = 0
    tables = {}
    for q in LOCAL_QUERIES:
        cols, rows = engine.query(sql_text(q))
        tables[q] = to_table(cols, rows)
        if write_expected:
            write_expected.mkdir(parents=True, exist_ok=True)
            write_csv(write_expected / (q[:-4] + ".csv"), tables[q])
            continue
        problems = check_result(q[:-4], cols, rows)
        failures += bool(problems)
        out(f"{'OK  ' if not problems else 'FAIL'} {q:<32} {len(rows):>2} rows  {tables[q][1:] if len(rows) == 1 else ''}")
    summaries = [["CustomerId", "Rows", "Revenue", "FirstOrderId", "LastOrderId"]]
    for c in PROC_CUSTOMERS:
        cols, rows = engine.query(proc_query(c))
        summaries.append(proc_summary(c, cols, rows)[1])
    if write_expected:
        write_csv(write_expected / "proc-customer-orders.csv", summaries)
        out(f"wrote {len(LOCAL_QUERIES) + 1} files to {write_expected}")
        return 0
    proc_problems = diff(read_csv(EXPECTED_DIR / "proc-customer-orders.csv"), summaries)
    failures += bool(proc_problems)
    out(f"{'OK  ' if not proc_problems else 'FAIL'} procedure query, customers 1 and 4242: "
        f"{summaries[1][1]} and {summaries[2][1]} rows")
    same = (tables[LOCAL_QUERIES[0]] == tables[LOCAL_QUERIES[1]], tables[LOCAL_QUERIES[2]] == tables[LOCAL_QUERIES[3]])
    out(f"rewrites return identical results: q01a = q01b {same[0]}, q02a = q02b {same[1]}")
    failures += not all(same)
    files = sorted(SQL_DIR.glob("*.sql"))
    checked = [f for f in files if f.name not in SQLSERVER_ONLY]
    errors = [e for f in checked for e in tsql_syntax_errors(f)]
    for e in errors:
        out(f"SYNTAX {e}")
    out(f"syntax: {len(checked) - len({e.split()[0] for e in errors})}/{len(checked)} T-SQL files parse "
        f"(sqlglot, tsql dialect); SQL Server only: {', '.join(sorted(SQLSERVER_ONLY))}")
    out("plans : SQL Server only - run with --engine sqlserver")
    return 1 if failures or errors else 0


# ---------------------------------------------------------------- SQL Server run
def unforce_all(engine: SqlServerEngine, out=print) -> None:
    cols, rows = engine.query("SELECT p.query_id, p.plan_id FROM sys.query_store_plan AS p "
                              "JOIN sys.query_store_query AS q ON q.query_id = p.query_id "
                              "WHERE p.is_forced_plan = 1 AND q.object_id = OBJECT_ID(N'Sales.GetCustomerOrders');")
    for q, p in rows:
        engine.run_batch(f"EXEC sp_query_store_unforce_plan @query_id = {int(q)}, @plan_id = {int(p)};")
        out(f"   unforced plan {p} (query {q}) left over from an earlier run")


def force_scan_plan(engine: SqlServerEngine, out=print) -> tuple[int, int] | None:
    cols, rows = engine.query(sql_text("qs-plans-for-procedure.sql"))
    out(f"\n-- qs-plans-for-procedure.sql (before forcing)\n{format_table(to_table(cols, rows))}")
    scans = [r for r in rows if r[cols.index("PlanShape")] == "clustered index scan"]
    if not scans:
        out("   FAIL Query Store has no clustered index scan plan for the procedure")
        return None
    q, p = int(scans[-1][cols.index("QueryId")]), int(scans[-1][cols.index("PlanId")])
    engine.run_batch(f"EXEC sp_query_store_force_plan @query_id = {q}, @plan_id = {p};")
    out(f"   EXEC sp_query_store_force_plan @query_id = {q}, @plan_id = {p};")
    return q, p


def run_scenario(engine: SqlServerEngine, sc: Scenario, save_plans: Path | None = None, out=print) -> list[RunResult]:
    out(f"\n== {sc.key}: {sc.title}")
    if sc.key == "sniffing":
        unforce_all(engine, out)
    forced = None
    if sc.key == "query-store":
        engine.run_batch(sql_text("psp-off.sql"))
        forced = force_scan_plan(engine, out)
    done: dict[str, RunResult] = {}
    table = [["run", "statement", "plan", "compiled/runtime", "pages read", "rows", "check"]]
    for n, run in enumerate(sc.runs, start=1):
        for b in run.before:
            engine.run_batch(sql_text(b))
        cols, rows, xml = engine.query_with_plan(sql_text(run.sql))
        plans = [p for doc in xml for p in showplan.parse_showplan(doc)]
        if not plans:
            raise RuntimeError(f"{sc.key}/{run.name}: SQL Server returned no plan")
        # EXEC of a procedure returns one document per statement: keep the one that reads tables
        plans = [p for p in plans if any(o.is_access for o in p.operators)] or plans
        if save_plans:
            save_plans.mkdir(parents=True, exist_ok=True)
            (save_plans / f"{sc.key}-{n}.sqlplan").write_text(
                re.sub(r"^\s*<\?xml[^>]*\?>", "", xml[-1]), encoding="utf-8")
        res = RunResult(run, plans[-1], check_result(run.expected, cols, rows), len(rows))
        res.failures = [m for c in run.checks if (m := evaluate(c, res, done))] + res.result_problems
        done[run.name] = res
        param = next((f"{p.compiled_value}/{p.runtime_value}" for p in res.plan.parameters
                      if p.name == "@CustomerId"), "-")
        stmt = run.sql if run.sql.endswith(".sql") else run.sql.replace("EXEC ", "").rstrip(";")
        table.append([f"{n} {run.name}", stmt, res.plan.access_summary(), param, str(res.plan.pages_read),
                      str(res.rows), "OK" if not res.failures else "FAIL"])
    out(format_table(table))
    for res in done.values():
        for w in all_warnings(res.plan):
            out(f"   warning ({res.run.name}): {w}")
        for f in res.failures:
            out(f"   FAIL {res.run.name}: {f}")
    if forced:
        for f in ("qs-plans-for-procedure.sql", "qs-forced-plans.sql"):
            cols, rows = engine.query(sql_text(f))
            out(f"\n-- {f}\n{format_table(to_table(cols, rows))}")
        failures = [r for r in rows if int(r[cols.index("PlanId")]) == forced[1]
                    and int(r[cols.index("ForceFailureCount")]) != 0]
        if failures or not any(int(r[cols.index("PlanId")]) == forced[1] for r in rows):
            msg = f"plan {forced[1]} is not forced cleanly: {failures or 'not listed as forced'}"
            done[sc.runs[-1].name].failures.append(msg)
            out(f"   FAIL {msg}")
        out(f"   plan {forced[1]} stays forced; undo with: "
            f"EXEC sp_query_store_unforce_plan @query_id = {forced[0]}, @plan_id = {forced[1]};")
    elif sc.key == "query-store":
        done[sc.runs[0].name].failures.append("no plan was forced")
    return list(done.values())


def run_sqlserver(engine: SqlServerEngine, setup: bool, only: str | None, save_plans: Path | None,
                  out=print) -> int:
    if setup:
        for f in (SETUP_FILE, INDEX_FILE, PROC_FILE):
            engine.run_file(SQL_DIR / f)
        out(f"setup: {SETUP_FILE}, {INDEX_FILE}, {PROC_FILE}")
    failed = total = 0
    for sc in SCENARIOS:
        if only and sc.key != only:
            continue
        results = run_scenario(engine, sc, save_plans, out)
        total += len(results)
        failed += sum(bool(r.failures) for r in results)
    out(f"\n{total - failed}/{total} runs behaved as expected on {engine.name}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--conn", default=os.environ.get("SQL_CONNECTION_STRING"),
                    help="SQL Server connection string (default: $SQL_CONNECTION_STRING)")
    ap.add_argument("--setup", action="store_true", help="sqlserver: load data, indexes and procedures first")
    ap.add_argument("--scenario", choices=[s.key for s in SCENARIOS])
    ap.add_argument("--save-plans", metavar="DIR", type=Path, help="sqlserver: write each actual plan as .sqlplan")
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
        return run_sqlserver(engine, a.setup, a.scenario, a.save_plans)
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
