"""Backup and recovery lab runner: full, differential and log backups of a FULL-recovery database, an accident,
and a point-in-time restore into a COPY, on SQL Server 2022 (CON-SQL01).

* ``sqlserver`` - the demo. Resets, creates ContosoBikesBackup (episode 5's tables, FULL recovery) and runs seven
  step files in order. Each step has checks (an expected error, no error) and, except the first, one result set
  that is compared with expected/. After the restore step it also asks the restore planner (restore_plan.py)
  to read msdb's backup history and checks that it picks the same four files the SQL restored.
* ``duckdb``    - the local check (no server, no Docker): runs the data statements of the lab (orders, the
  accident, the repair) on a model in which "restoring to the mark" is a copy of the tables taken at the mark,
  and compares the counts with expected/. BACKUP and RESTORE themselves need SQL Server.

    python src/backup_lab.py                                    # duckdb: the data model
    python src/backup_lab.py --engine sqlserver --setup         # needs SQL_CONNECTION_STRING
    python src/backup_lab.py --engine sqlserver --plan          # print the planner's RESTORE statements
    python src/backup_lab.py --engine sqlserver --reset-only    # tear-down: drops both databases and their history
"""
from __future__ import annotations

import argparse
import ntpath
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import restore_plan  # noqa: E402
from labdb import (DuckDBEngine, ScriptResult, SqlServerEngine, diff, format_table, read_csv,  # noqa: E402
                   to_table)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
LIVE_DB, COPY_DB = "ContosoBikesBackup", "ContosoBikesRecovered"
SETUP_FILES = ["b00-reset.sql", "00-create-database.sql"]
EXPECTED_FILES = ["MGLab_ContosoBikesBackup_Full.bak", "MGLab_ContosoBikesBackup_Diff.bak",
                  "MGLab_ContosoBikesBackup_Log1.trn", "MGLab_ContosoBikesBackup_Log2.trn"]
LOGICAL_FILES = {LIVE_DB: "{data}MGLab_ContosoBikesRecovered.mdf",
                 LIVE_DB + "_log": "{log}MGLab_ContosoBikesRecovered_log.ldf"}


@dataclass
class Step:
    key: str                                   # src/sql/<key>.sql and expected/<key>.csv
    title: str
    before: list[str] = field(default_factory=list)   # data files, run in LIVE_DB before the step
    checks: list[str] = field(default_factory=lambda: ["error: none"])
    result: bool = True                        # the step ends with a result set compared with expected/
    plan_check: bool = False                   # afterwards: the restore planner must pick the same files


STEPS = [
    Step("b01-log-before-full", "FULL recovery, no full backup yet: a log backup is refused",
         checks=["error: contains: no current database backup"], result=False),
    Step("b02-full-backup", "the first full backup, with checksums and compression"),
    Step("b03-differential-backup", "a differential backup, based on that full", before=["d01-orders-after-full.sql"]),
    Step("b04-log-backup", "the first log backup", before=["d02-order-after-diff.sql"]),
    Step("b05-incident", "an UPDATE without WHERE, one good order after it, and a log backup that holds both"),
    Step("b06-restore-copy", "full + differential + 2 logs restored to a copy, stopped just before the UPDATE",
         plan_check=True),
    Step("b07-verify-and-repair", "CHECKSUM and CHECKDB, then repair the live database from the copy"),
]


def sql_text(name: str) -> str:
    return (SQL_DIR / (name if name.endswith(".sql") else f"{name}.sql")).read_text(encoding="utf-8")


def evaluate(check: str, res: ScriptResult) -> str | None:
    kind, _, arg = check.partition(":")
    arg = arg.strip()
    if kind == "error" and arg == "none":
        return None if not res.errors else f"unexpected error: {res.errors[0][:200]}"
    if kind == "error" and arg.startswith("contains:"):
        needle = arg.split(":", 1)[1].strip().lower()
        if not res.errors:
            return "expected an error, none was raised"
        return None if any(needle in e.lower() for e in res.errors) else f"error does not mention {needle!r}: {res.errors[0][:200]}"
    raise ValueError(f"unknown check: {check}")


# ---------------------------------------------------------------- local: the data model
def local_table(eng: DuckDBEngine, sql: str) -> list[list[str]]:
    columns, rows = eng.query(sql)
    return to_table(columns, rows)


def final_select(name: str) -> str:
    """The step's result query: the last batch of the file."""
    from labdb import split_batches
    return split_batches(sql_text(name))[-1]


def run_local() -> int:
    eng = DuckDBEngine(schemas=())
    problems: list[str] = []
    try:
        for db in (LIVE_DB, COPY_DB):
            eng.con.execute(f"ATTACH ':memory:' AS {db}")
        eng.con.execute(f"CREATE SCHEMA {COPY_DB}.Sales")
        eng.con.execute(f"USE {LIVE_DB}")
        eng.con.execute("CREATE SCHEMA Sales")
        eng.run_file(SQL_DIR / "01-schema-and-data.sql")
        eng.run_file(SQL_DIR / "d01-orders-after-full.sql")
        eng.run_file(SQL_DIR / "d02-order-after-diff.sql")
        # "the mark": the live tables right now are what a restore stopped at the mark brings back
        for table in ("Customers", "Products", "Orders", "OrderLines"):
            eng.con.execute(f"CREATE TABLE {COPY_DB}.Sales.{table} AS SELECT * FROM Sales.{table}")
        print("model: seed + 2 orders + 1 order loaded; copy taken at the mark (= the result of a restore with STOPAT)")

        eng.run_file(SQL_DIR / "b05-incident.sql")                # UPDATE without WHERE, order 1012 (sqlserver-only batches skipped)
        got = local_table(eng, final_select("b05-incident"))
        print("\nb05-incident: live database after the accident"); print(format_table(got))
        problems += [f"b05: {p}" for p in diff(read_csv(EXPECTED_DIR / "b05-incident.csv"), got)]

        copy_counts = local_table(eng, f"""
            SELECT N'Products priced at 0 in the copy' AS Item, CAST(COUNT(*) AS varchar) AS Result FROM {COPY_DB}.Sales.Products WHERE ListPrice = 0
            UNION ALL SELECT N'Orders in the copy', CAST(COUNT(*) AS varchar) FROM {COPY_DB}.Sales.Orders
            UNION ALL SELECT N'Order 1012 in the copy', CAST(COUNT(*) AS varchar) FROM {COPY_DB}.Sales.Orders WHERE OrderId = 1012""")
        print("\nb06-restore-copy: the copy (the RESTORING/ONLINE state row needs SQL Server)"); print(format_table(copy_counts))
        expected = [r for r in read_csv(EXPECTED_DIR / "b06-restore-copy.csv") if r[0] != "Recovered copy state"]
        problems += [f"b06: {p}" for p in diff(expected, copy_counts)]

        # the repair: the UPDATE of b07 (copy -> live), then its result query, both from the file
        from labdb import split_batches
        repair = [b for b in split_batches(sql_text("b07-verify-and-repair")) if b.lstrip().startswith("UPDATE")]
        assert len(repair) == 1
        eng.execute(repair[0])
        got = local_table(eng, final_select("b07-verify-and-repair"))
        print("\nb07-verify-and-repair: live database after the repair"); print(format_table(got))
        problems += [f"b07: {p}" for p in diff(read_csv(EXPECTED_DIR / "b07-verify-and-repair.csv"), got)]
    finally:
        eng.close()
    print("\n" + ("local checks: the data model matches expected/ on duckdb" if not problems
                  else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def use(engine: SqlServerEngine, db: str) -> None:
    res = engine.run_script(f"USE {db};")
    if res.errors:
        raise RuntimeError(res.errors[0])


def history(engine: SqlServerEngine) -> tuple[list[restore_plan.BackupRow], object]:
    """The planner's input, read from msdb, and the mark (the moment just before the accident)."""
    res = engine.run_script(sql_text("msdb-history.sql"))
    if res.errors:
        raise RuntimeError(res.errors[0])
    rows = [restore_plan.BackupRow(kind=r[0], start=r[1], finish=r[2], first_lsn=r[3], last_lsn=r[4],
                                   copy_only=bool(r[6]), device=r[7]) for r in res.rows]
    mark = engine.run_script(f"SELECT MarkTime FROM {LIVE_DB}.dbo.RecoveryMarks WHERE Name = N'before-bad-update';")
    if mark.errors or not mark.rows:
        raise RuntimeError("no recovery mark: run b05-incident first")
    return rows, mark.rows[0][0]


def planner_statements(engine: SqlServerEngine) -> tuple[restore_plan.Plan, list[str]]:
    rows, target = history(engine)
    plan = restore_plan.build_plan(rows, target)
    info = engine.run_script("SELECT CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath')), "
                             "CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultLogPath'));")
    data, log = (p if p.endswith("\\") else p + "\\" for p in info.rows[0])
    moves = {k: v.format(data=data, log=log) for k, v in LOGICAL_FILES.items()}
    return plan, restore_plan.render(plan, COPY_DB, moves)


def check_planner(engine: SqlServerEngine) -> list[str]:
    plan, statements = planner_statements(engine)
    names = [ntpath.basename(f) for f in plan.files]
    print("  planner picked: " + " -> ".join(names))
    for s in statements:
        print("    " + s)
    problems = [] if names == EXPECTED_FILES else [f"planner picked {names}, expected {EXPECTED_FILES}"]
    return problems + plan.warnings


def run_sqlserver(engine: SqlServerEngine, steps: list[Step], setup: bool) -> int:
    if setup:
        for f in SETUP_FILES:
            engine.run_file(SQL_DIR / f)
        use(engine, LIVE_DB)
        engine.run_file(SQL_DIR / "01-schema-and-data.sql")
        print(f"setup: {LIVE_DB} created (FULL recovery) with episode 5's tables and data; nothing backed up yet")
    failures = 0
    for step in steps:
        for f in step.before:
            use(engine, LIVE_DB)
            engine.run_file(SQL_DIR / f)
            print(f"\nran {f}")
        res = engine.run_script(sql_text(step.key))
        print(f"\n{step.key}: {step.title}")
        problems = [f"{c}: {why}" for c in step.checks if (why := evaluate(c, res))]
        for c in step.checks:
            print(f"  check {c:<52} {'OK' if not any(p.startswith(c + ':') for p in problems) else 'FAILED'}")
        if step.result:
            if res.columns is None:
                problems.append("no result set")
            else:
                table = to_table(res.columns, res.rows)
                print(format_table(table))
                problems += diff(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)
        if step.plan_check and not problems:
            problems += check_planner(engine)
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(steps) - failures}/{len(steps)} steps behaved as expected on sqlserver")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: reset and recreate the database first")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: run b00-reset.sql and stop")
    ap.add_argument("--plan", action="store_true", help="sqlserver: print the restore planner's statements and stop")
    ap.add_argument("--step", action="append", help="run only these steps (repeatable; they build on each other)")
    a = ap.parse_args(argv)

    steps = [s for s in STEPS if not a.step or s.key in a.step]
    if a.step and len(steps) != len(a.step):
        ap.error(f"unknown step; choose from {[s.key for s in STEPS]}")
    if a.engine == "duckdb":
        return run_local()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")
    eng = SqlServerEngine(conn_str)
    try:
        if a.reset_only:
            eng.run_file(SQL_DIR / "b00-reset.sql")
            print("reset: both databases dropped, their msdb backup history deleted (the backup files stay on disk)")
            return 0
        if a.plan:
            for s in planner_statements(eng)[1]:
                print(s)
            return 0
        return run_sqlserver(eng, steps, a.setup)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
