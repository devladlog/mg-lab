"""High availability and disaster recovery lab runner (DEVLADLOG SQL #9): hand-built LOG SHIPPING between two databases
on CON-SQL01, two gotchas, a failover drill with a stopwatch, and an RPO exposure report from msdb.

Primary ``ContosoBikesHA`` (episode 5's tables, FULL recovery); standby ``ContosoBikesHA_Standby`` (restored WITH
STANDBY, readable between log restores). One instance holds both, so this drill covers "the database is lost or
damaged", not "the server is lost": real log shipping puts the standby on another server (see README).

* ``sqlserver`` - the demo. Needs SQL_CONNECTION_STRING (sysadmin on the lab instance). Ten steps, each compared with
  expected/ (``*`` = any value, for times): the RPO report before anything is backed up, the standby, a shipped log,
  a write on the standby (error 3906), a rogue log backup that breaks the chain (error 4305), the repair, the failover
  (tail-log backup + restore WITH RECOVERY, timed), a write on the promoted copy, the RPO report after.
* ``duckdb``    - the local check: the order counts of the drill on a model in which "ship a log" is a copy of the
  tables. BACKUP, RESTORE, msdb and the two errors need SQL Server.

    python src/ha_lab.py                                          # duckdb
    python src/ha_lab.py --engine sqlserver --setup               # needs SQL_CONNECTION_STRING
    python src/ha_lab.py --engine sqlserver --report --rpo 15     # RPO verdicts for every user database
    python src/ha_lab.py --engine sqlserver --reset-only          # tear-down: both databases and their history
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dr_report  # noqa: E402
from labdb import (DuckDBEngine, ScriptResult, SqlServerEngine, format_table, read_csv,  # noqa: E402
                   split_batches, to_table)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
PRIMARY, STANDBY = "ContosoBikesHA", "ContosoBikesHA_Standby"
SETUP_FILES = ["h00-reset.sql", "00-create-database.sql"]
EXPECTED_FILES = ["MGLab_ContosoBikesHA_Full.bak", "MGLab_ContosoBikesHA_Log1.trn", "MGLab_ContosoBikesHA_Rogue.trn",
                  "MGLab_ContosoBikesHA_Log2.trn", "MGLab_ContosoBikesHA_Tail.trn"]
FAILOVER_LIMIT_SECONDS = 60.0     # our target for this drill (tail-log backup + restore of a few KB), not a Microsoft figure
DEFAULT_RPO_MINUTES = 15


@dataclass
class Step:
    key: str                                           # expected/<key>.csv
    title: str
    sql: str | None = None                             # src/sql/<sql>.sql, default: the key
    before: list[str] = field(default_factory=list)    # data files, run in the primary before the step
    checks: list[str] = field(default_factory=lambda: ["error: none"])
    prefix: str | None = None                          # keep only result rows whose first column starts with this
    rpo: bool = False                                  # also print the RPO verdicts for the rows
    limit: float | None = None                         # the step must finish within this many seconds


STEPS = [
    Step("h01-rpo-before", "RPO exposure before any backup", sql="h01-rpo-exposure", prefix=PRIMARY, rpo=True),
    Step("h02-init-standby", "full backup, restored as the standby WITH STANDBY"),
    Step("h03-ship-log", "order 1009, then one log-shipping cycle", before=["d01-order-1009.sql"]),
    Step("h04-standby-write", "gotcha: a write on the standby", checks=["error: contains: database is read-only"]),
    Step("h05-rogue-log-backup", "order 1010, then a log backup nobody ships", before=["d02-order-1010.sql"]),
    Step("h06-ship-log-fails", "order 1011, then the next cycle: the chain is broken", before=["d03-order-1011.sql"],
         checks=["error: contains: too recent to apply"]),
    Step("h07-repair-chain", "restore the missing log first, then the failed one"),
    Step("h08-failover", "order 1012, tail-log backup, restore WITH RECOVERY (timed)", before=["d04-order-1012.sql"],
         limit=FAILOVER_LIMIT_SECONDS),
    Step("h09-write-on-promoted", "a write on the promoted copy"),
    Step("h10-rpo-after", "RPO exposure after the failover", sql="h01-rpo-exposure", prefix=PRIMARY, rpo=True),
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


def diff_wild(expected: list[list[str]], actual: list[list[str]]) -> list[str]:
    """Like labdb.diff, but ``*`` in expected/ matches any value (times and minutes change on every run)."""
    problems = []
    if expected[0] != actual[0]:
        problems.append(f"columns: expected {expected[0]}, got {actual[0]}")
    if len(expected) != len(actual):
        problems.append(f"rows: expected {len(expected) - 1}, got {len(actual) - 1}")
    for i, (e, a) in enumerate(zip(expected[1:], actual[1:]), start=1):
        if len(e) != len(a) or any(x != "*" and x != y for x, y in zip(e, a)):
            problems.append(f"row {i}: expected {e}, got {a}")
    return problems


# ---------------------------------------------------------------- local: DuckDB model
def count(eng: DuckDBEngine, db: str, where: str = "") -> int:
    return eng.query(f"SELECT COUNT(*) FROM {db}.Sales.Orders {where}")[1][0][0]


def ship(eng: DuckDBEngine) -> None:
    """'Restore the log on the standby' as a model: the standby's tables become the primary's tables right now."""
    for t in ("Customers", "Products", "Orders", "OrderLines"):
        eng.con.execute(f"CREATE OR REPLACE TABLE {STANDBY}.Sales.{t} AS SELECT * FROM {PRIMARY}.Sales.{t}")


def run_local() -> int:
    eng = DuckDBEngine(schemas=())
    problems: list[str] = []

    def check(key: str, got: list[tuple[str, int]]) -> None:
        table = [["Item", "Result"]] + [[k, str(v)] for k, v in got]
        want = [r for r in read_csv(EXPECTED_DIR / f"{key}.csv")[1:] if r[0] in {k for k, _ in got}]
        print(f"\n{key}"); print(format_table(table))
        problems.extend(f"{key}: {p}" for p in
                        (["rows differ: expected " + str(want) + ", got " + str(table[1:])] if want != table[1:] else []))

    try:
        for db in (PRIMARY, STANDBY):
            eng.con.execute(f"ATTACH ':memory:' AS {db}")
            eng.con.execute(f"CREATE SCHEMA {db}.Sales")
        eng.con.execute(f"USE {PRIMARY}")
        eng.run_file(SQL_DIR / "01-schema-and-data.sql")
        print("model: episode 5's seed on the primary; 'ship a log' = copy the tables to the standby")

        ship(eng)                                                           # h02: full backup + restore
        check("h02-init-standby", [("Orders on the primary", count(eng, PRIMARY)), ("Orders on the standby", count(eng, STANDBY))])
        eng.run_file(SQL_DIR / "d01-order-1009.sql"); ship(eng)             # h03
        check("h03-ship-log", [("Orders on the primary", count(eng, PRIMARY)), ("Orders on the standby", count(eng, STANDBY))])
        check("h04-standby-write", [("Orders on the standby", count(eng, STANDBY)),
                                    ("Order 9999 on the standby", count(eng, STANDBY, "WHERE OrderId = 9999"))])
        eng.run_file(SQL_DIR / "d02-order-1010.sql")                        # h05: a log backup nobody ships
        eng.run_file(SQL_DIR / "d03-order-1011.sql")                        # h06: Log2 cannot be applied: standby unchanged
        check("h06-ship-log-fails", [("Orders on the primary", count(eng, PRIMARY)), ("Orders on the standby", count(eng, STANDBY))])
        ship(eng)                                                           # h07: rogue, then Log2
        check("h07-repair-chain", [("Orders on the primary", count(eng, PRIMARY)), ("Orders on the standby", count(eng, STANDBY))])
        eng.run_file(SQL_DIR / "d04-order-1012.sql"); ship(eng)             # h08: the tail holds order 1012
        check("h08-failover", [("Orders on the promoted copy", count(eng, STANDBY)),
                               ("Order 1012 on the promoted copy", count(eng, STANDBY, "WHERE OrderId = 1012"))])
        for batch in split_batches(sql_text("h09-write-on-promoted")):      # h09: the file's INSERTs and result query
            cur = eng.execute(batch)
        got = to_table([d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()])
        print("\nh09-write-on-promoted"); print(format_table(got))
        problems += [f"h09: {p}" for p in ([] if got == read_csv(EXPECTED_DIR / "h09-write-on-promoted.csv")
                                           else [f"expected {read_csv(EXPECTED_DIR / 'h09-write-on-promoted.csv')}, got {got}"])]
    finally:
        eng.close()
    print("\n" + ("local checks: the order counts of the drill match expected/ on duckdb (BACKUP, RESTORE and the errors need SQL Server)"
                  if not problems else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def use(engine: SqlServerEngine, db: str) -> None:
    res = engine.run_script(f"USE {db};")
    if res.errors:
        raise RuntimeError(res.errors[0])


def keep_rows(res: ScriptResult, prefix: str | None) -> list[tuple]:
    return [r for r in res.rows if prefix is None or str(r[0]).startswith(prefix)]


def run_sqlserver(engine: SqlServerEngine, steps: list[Step], setup: bool, rpo: int = DEFAULT_RPO_MINUTES,
                  clock=time.monotonic) -> int:
    if setup:
        for f in SETUP_FILES:
            engine.run_file(SQL_DIR / f)
        use(engine, PRIMARY)
        engine.run_file(SQL_DIR / "01-schema-and-data.sql")
        print(f"setup: {PRIMARY} created (FULL recovery) with episode 5's tables and data; nothing backed up yet")
    failures = 0
    for step in steps:
        print(f"\n{step.key}: {step.title}")
        problems: list[str] = []
        for f in step.before:
            use(engine, PRIMARY)
            engine.run_file(SQL_DIR / f)
            print(f"  ran {f}")
        use(engine, "master")
        t0 = clock()
        res = engine.run_script(sql_text(step.sql or step.key))
        elapsed = clock() - t0
        problems += [f"{c}: {why}" for c in step.checks if (why := evaluate(c, res))]
        for c in step.checks:
            print(f"  check {c:<46} {'OK' if not any(p.startswith(c + ':') for p in problems) else 'FAILED'}")
        if step.limit is not None:
            print(f"  step took {elapsed:.1f} s (limit {step.limit:.0f} s)")
            if elapsed > step.limit:
                problems.append(f"took {elapsed:.1f} s, limit {step.limit:.0f} s")
        if res.columns is None:
            problems.append("no result set")
        else:
            rows = keep_rows(res, step.prefix)
            table = to_table(res.columns, rows)
            print(format_table(table))
            problems += diff_wild(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)
            if step.rpo:
                print("  RPO verdicts (target %d min):" % rpo)
                print("  " + dr_report.render(dr_report.assess(rows, rpo)).replace("\n", "\n  "))
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(steps) - failures}/{len(steps)} steps behaved as expected on sqlserver")
    return 1 if failures else 0


def report(engine: SqlServerEngine, rpo: int) -> int:
    use(engine, "master")
    res = engine.run_script(sql_text("h01-rpo-exposure"))
    if res.errors or res.columns is None:
        print("report FAILED: " + (res.errors[0][:200] if res.errors else "no result set"))
        return 1
    verdicts = dr_report.assess(res.rows, rpo)
    print(dr_report.render(verdicts))
    return 1 if any(v.verdict in (dr_report.AT_RISK, dr_report.NO_BACKUP) for v in verdicts) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: reset and recreate the primary first")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: run h00-reset.sql and stop")
    ap.add_argument("--report", action="store_true", help="sqlserver: RPO verdicts for every user database (exit 1 if one is AT RISK or has NO BACKUP)")
    ap.add_argument("--rpo", type=int, default=DEFAULT_RPO_MINUTES, help="RPO target in minutes (default %(default)s)")
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
            eng.run_file(SQL_DIR / "h00-reset.sql")
            print("reset: both databases dropped, their msdb history deleted (backup files and the undo file stay on disk)")
            return 0
        if a.report:
            return report(eng, a.rpo)
        return run_sqlserver(eng, steps, a.setup, a.rpo)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
