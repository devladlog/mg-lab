"""Performance tuning lab runner (DEVLADLOG SQL #8): a configuration review, the most expensive statements, a REAL
blocking incident diagnosed from the DMVs and fixed with row versioning, and wait statistics measured as the
difference between two snapshots. Data: episode 4's ContosoBikesPerf (200,000 orders).

* ``sqlserver`` - the demo. Needs SQL_CONNECTION_STRING (any database; the runner issues USE). Three steps:
    t01-config-review  sys.configurations and dm_os_sys_info, compared with expected/ (``*`` = any value)
    t02-top-queries    runs the workload (3 scans, 50 seeks), reads dm_exec_query_stats
    t03-blocking       three connections: A holds an open UPDATE, B reads the row and waits (LCK_M_S), C diagnoses
                       it from the DMVs; A rolls back. Then READ_COMMITTED_SNAPSHOT is turned on and the same
                       round runs again: B no longer waits. Wait-statistics snapshots surround each round and
                       Tune.usp_WaitDelta subtracts them. The results become two small tables (expected/t03-blocking.csv,
                       expected/t04-wait-delta.csv).
* ``duckdb``    - the local check: the lab's data, the workload statements, the UPDATE/ROLLBACK of the blocker and
                  the delta query (extracted from usp_WaitDelta) on made-up snapshots. No locks, DMVs or waits.

    python src/perf_lab.py                                    # duckdb
    python src/perf_lab.py --engine sqlserver --setup         # needs SQL_CONNECTION_STRING
    python src/perf_lab.py --engine sqlserver --reset-only    # tear-down: RCSI off, Tune objects dropped
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from labdb import (DuckDBEngine, SqlServerEngine, diff, format_table, is_sqlserver_only, read_csv,  # noqa: E402
                   split_batches, to_table)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
DB = "ContosoBikesPerf"
HOLD_SECONDS = 3.0          # how long the writer keeps the lock once the reader is seen waiting
BLOCK_TIMEOUT = 20.0        # seconds to wait for the reader to show up as blocked (or to finish)
RCSI_FAST_SECONDS = 2.0
DELTA_START, DELTA_END = "-- delta-query-begin", "-- delta-query-end"


def sql_text(name: str) -> str:
    return (SQL_DIR / (name if name.endswith(".sql") else f"{name}.sql")).read_text(encoding="utf-8")


# ---------------------------------------------------------------- comparing: '*' matches any value
def diff_wild(expected: list[list[str]], actual: list[list[str]]) -> list[str]:
    problems = []
    if expected[0] != actual[0]:
        problems.append(f"columns: expected {expected[0]}, got {actual[0]}")
    if len(expected) != len(actual):
        problems.append(f"rows: expected {len(expected) - 1}, got {len(actual) - 1}")
    for i, (e, a) in enumerate(zip(expected[1:], actual[1:]), start=1):
        if len(e) != len(a) or any(x != "*" and x != y for x, y in zip(e, a)):
            problems.append(f"row {i}: expected {e}, got {a}")
    return problems


def yes(flag: bool) -> str:
    return "yes" if flag else "no"


# ---------------------------------------------------------------- local: DuckDB
def extract_delta_query() -> str:
    """The query between the markers in usp_WaitDelta, as one statement."""
    text = sql_text("10-tune-tools")
    body = text.split(DELTA_START, 1)[1].split(DELTA_END, 1)[0]
    return body.strip().rstrip(";")


# made-up snapshots: (wait type, tasks, wait ms, signal ms)
SNAP_A = [("LCK_M_S", 1, 100, 0), ("WRITELOG", 10, 400, 20), ("SOS_SCHEDULER_YIELD", 500, 900, 880),
          ("PAGEIOLATCH_SH", 40, 300, 5), ("CXPACKET", 7, 70, 1), ("SLEEP_TASK", 1000, 50000, 100),
          ("LAZYWRITER_SLEEP", 100, 90000, 0)]
SNAP_B = [("LCK_M_S", 2, 5100, 0), ("WRITELOG", 30, 700, 40), ("SOS_SCHEDULER_YIELD", 900, 1500, 1450),
          ("PAGEIOLATCH_SH", 45, 320, 6), ("CXPACKET", 7, 70, 1), ("SLEEP_TASK", 5000, 90000, 150),
          ("LAZYWRITER_SLEEP", 140, 130000, 0), ("LCK_M_IX", 1, 250, 0)]
SNAP_EXPECTED = [["WaitType", "WaitingTasksDelta", "WaitTimeMsDelta", "SignalWaitTimeMsDelta"],
                 ["LCK_M_S", "1", "5000", "0"], ["SOS_SCHEDULER_YIELD", "400", "600", "570"],
                 ["WRITELOG", "20", "300", "20"], ["LCK_M_IX", "1", "250", "0"], ["PAGEIOLATCH_SH", "5", "20", "1"]]


def local_delta(eng: DuckDBEngine, top: int = 5) -> list[list[str]]:
    eng.run_file(SQL_DIR / "10-tune-tools.sql")           # creates Tune.WaitSnapshot (the other batches are sqlserver-only)
    for label, snap in (("a", SNAP_A), ("b", SNAP_B)):
        for w in snap:
            eng.con.execute("INSERT INTO Tune.WaitSnapshot VALUES (?, ?, ?, ?, ?)", [label, *w])
    columns, rows = eng.query(delta_sql())
    return to_table(columns, rows[:top])


def delta_sql() -> str:
    """The delta query with the labels filled in and TOP (@Top) removed: DuckDB 2.0.1 returned too many rows for
    LIMIT n on this query (a DuckDB quirk, found by the test of TOP), so the local check cuts the rows in Python.
    TOP itself is plain T-SQL and runs on SQL Server."""
    return (extract_delta_query().replace("TOP (@Top)", "").replace("@FromLabel", "N'a'").replace("@ToLabel", "N'b'"))


def bare(sql: str) -> str:
    """The statement without comments (sqlglot attaches comments to statements; the local check runs plain SQL)."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--")).strip()


def strip_assignment(statement: str) -> str:
    """'SELECT @n = COUNT(*) ...' -> 'SELECT COUNT(*) ...' (variables do not exist in the DuckDB check)."""
    return re.sub(r"^SELECT @\w+ = ", "SELECT ", statement)


def workload_statements() -> dict[str, str]:
    found = {}
    for m in re.finditer(r"N'(SELECT @(?:n|status) = .*?mglab-w-(scan|seek) \*/;)'", sql_text("w01-workload"), re.DOTALL):
        found[m.group(2)] = strip_assignment(m.group(1)).replace("@id", "1")
    return found


def run_local() -> int:
    problems: list[str] = []
    eng = DuckDBEngine(schemas=("Sales", "Tune"))
    try:
        eng.run_file(SQL_DIR / "01-schema-and-data.sql")
        n = eng.query("SELECT COUNT(*) FROM Sales.Orders")[1][0][0]
        print(f"data: {n} orders loaded (episode 4's data set)")
        if n != 200000:
            problems.append(f"orders: expected 200000, got {n}")

        work = workload_statements()
        if set(work) != {"scan", "seek"}:
            problems.append(f"w01-workload: found {sorted(work)}, expected scan and seek")
        else:
            scan = eng.query(work["scan"])[1][0][0]
            seek = eng.query(work["seek"])[1][0][0]
            print(f"workload: the scan counts {scan} orders from 2025, the seek reads order 1 -> {seek!r}")
            if not scan or seek != "Shipped":
                problems.append(f"workload results: scan={scan}, seek={seek!r}")

        eng.execute(bare(sql_text("t03a-blocker")))
        inside = eng.query("SELECT Status FROM Sales.Orders WHERE OrderId = 1")[1][0][0]
        eng.execute(bare(sql_text("t03d-release")))
        after = eng.query(bare(sql_text("t03b-reader")))[1][0][0]
        print(f"blocker: inside the open transaction the row says {inside!r}; after the ROLLBACK the reader gets {after!r}")
        if (inside, after) != ("Cancelled", "Shipped"):
            problems.append(f"blocker/rollback: {inside!r} then {after!r}")

        got = local_delta(eng)
        print("\nusp_WaitDelta's query on made-up snapshots (top 5; SLEEP_TASK and LAZYWRITER_SLEEP are background noise, CXPACKET did not change):")
        print(format_table(got))
        problems += [f"delta: {p}" for p in diff(SNAP_EXPECTED, got)]
    finally:
        eng.close()
    print("\n" + ("local checks: workload, rollback and wait-delta query behave as expected on duckdb"
                  if not problems else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def use(engine: SqlServerEngine, db: str) -> None:
    res = engine.run_script(f"USE {db};")
    if res.errors:
        raise RuntimeError(res.errors[0])


def open_session(connect, db: str = DB) -> SqlServerEngine:
    eng = SqlServerEngine(connection=connect())
    use(eng, db)
    return eng


def run_one(engine: SqlServerEngine, name: str):
    res = engine.run_script(sql_text(name))
    if res.errors:
        raise RuntimeError(f"{name}: {res.errors[0]}")
    return res


def snapshot(engine: SqlServerEngine, label: str) -> None:
    res = engine.run_script(f"EXEC Tune.usp_TakeWaitSnapshot @Label = N'{label}';")
    if res.errors:
        raise RuntimeError(f"snapshot {label}: {res.errors[0]}")


@dataclass
class Round:
    writer_spid: object = None
    diag: list[tuple] = field(default_factory=list)       # rows of t03c-diagnose while the reader waited
    diag_cols: list[str] = field(default_factory=list)
    reader_status: object = None
    reader_seconds: float = 0.0
    reader_errors: list[str] = field(default_factory=list)
    reader_finished: bool = False


def one_round(connect, expect_block: bool, sleep=time.sleep, clock=time.monotonic) -> Round:
    """A (writer, open transaction), B (reader, in a thread), C (diagnoser). Returns what each saw."""
    r = Round()
    a, c = open_session(connect), open_session(connect)
    out: dict = {}

    def reader() -> None:
        b = open_session(connect)
        t0 = clock()
        try:
            res = b.run_script(sql_text("t03b-reader"))
            out["errors"] = res.errors
            out["status"] = res.rows[0][0] if res.rows else None
        except Exception as e:  # noqa: BLE001
            out["errors"] = [str(e)]
        finally:
            out["seconds"] = clock() - t0
            b.close()

    try:
        r.writer_spid = a.run_script("SELECT @@SPID;").rows[0][0]
        run_one(a, "t03a-blocker")
        th = threading.Thread(target=reader, daemon=True)
        th.start()
        deadline = clock() + BLOCK_TIMEOUT
        while clock() < deadline:
            d = run_one(c, "t03c-diagnose")
            if d.rows:
                r.diag, r.diag_cols = d.rows, d.columns
                break
            if not th.is_alive():          # the reader is done: it was not blocked (or never will be)
                break
            sleep(0.5)
        if r.diag:
            sleep(HOLD_SECONDS)            # keep the lock long enough to measure the wait
        a.run_script(sql_text("t03d-release"))
        th.join(BLOCK_TIMEOUT)
        r.reader_finished = not th.is_alive()
    finally:
        a.close()
        c.close()
    r.reader_status, r.reader_seconds = out.get("status"), out.get("seconds", 0.0)
    r.reader_errors = out.get("errors", ["reader did not finish"] if not out else [])
    return r


def col(r: Round, name: str):
    return r.diag[0][r.diag_cols.index(name)] if r.diag else None


def blocking_tables(first: Round, second: Round, delta1, delta2) -> tuple[list[list[str]], list[list[str]]]:
    """The two result tables compared with expected/. delta1/delta2 are (columns, rows) of usp_WaitDelta."""
    wait = col(first, "WaitType")
    blocking = [["Check", "Result"],
                ["Reader blocked by the open transaction", yes(bool(first.diag))],
                ["Wait type of the blocked reader", str(wait) if wait else "none"],
                ["Blocker session is the writer", yes(bool(first.diag) and col(first, "BlockerSession") == first.writer_spid)],
                ["Blocker holds an open transaction", yes(bool(first.diag) and (col(first, "BlockerOpenTransactions") or 0) >= 1)],
                ["Blocker last statement is the UPDATE", yes(bool(first.diag) and "UPDATE Sales.Orders" in str(col(first, "BlockerLastStatement")))],
                ["Reader result after the rollback", str(first.reader_status)],
                ["RCSI reader result while the writer is still open", str(second.reader_status)],
                ["RCSI reader waited under 2 seconds",
                 yes(second.reader_finished and not second.diag and second.reader_seconds < RCSI_FAST_SECONDS)]]
    cols1, rows1 = delta1
    cols2, rows2 = delta2
    blocked_ms = first.reader_seconds * 1000
    lock_ms = next((row[cols1.index("WaitTimeMsDelta")] for row in rows1 if row[0] == "LCK_M_S"), 0)
    rcsi_locks = [row[0] for row in rows2 if str(row[0]).startswith("LCK_M_")]
    waits = [["Check", "Result"],
             ["Top watch-list wait without RCSI", str(rows1[0][0]) if rows1 else "none"],
             ["Lock wait covers the time the reader was blocked", yes(blocked_ms > 0 and lock_ms >= 0.8 * blocked_ms)],
             ["Lock waits (LCK_M_*) with RCSI", ", ".join(rcsi_locks) if rcsi_locks else "none"]]
    return blocking, waits


def blocking_phase(connect, sleep=time.sleep, clock=time.monotonic) -> tuple[list[list[str]], list[list[str]]]:
    admin = open_session(connect)
    master = None
    try:
        print("  snapshot 'before-blocking'; round 1: row locked by an open UPDATE, reader waits ...")
        snapshot(admin, "before-blocking")
        first = one_round(connect, True, sleep, clock)
        snapshot(admin, "after-blocking")
        d1 = run_one(admin, "t04-wait-delta")
        delta1 = (d1.columns or [], d1.rows)
        print(f"  round 1: blocked={bool(first.diag)}, reader waited {first.reader_seconds:.1f}s and read {first.reader_status!r}")
        admin.close()
        admin = None
        master = open_session(connect, "master")           # no other connection may use the database now
        run_one(master, "t03e-enable-rcsi")
        master.close()
        master = None
        print("  READ_COMMITTED_SNAPSHOT ON; round 2 ...")
        admin = open_session(connect)
        snapshot(admin, "before-rcsi")
        second = one_round(connect, False, sleep, clock)
        snapshot(admin, "after-rcsi")
        d2 = run_one(admin, "t04b-wait-delta-after-rcsi")
        delta2 = (d2.columns or [], d2.rows)
        print(f"  round 2: blocked={bool(second.diag)}, reader waited {second.reader_seconds:.1f}s and read {second.reader_status!r}")
    finally:
        for e in (admin, master):
            if e is not None:
                e.close()
    return blocking_tables(first, second, delta1, delta2)


@dataclass
class Step:
    key: str
    title: str
    before: list[str] = field(default_factory=list)


STEPS = [Step("t01-config-review", "configuration review: memory, MAXDOP, cost threshold"),
         Step("t02-top-queries", "the workload, then the most expensive statements", before=["w01-workload"]),
         Step("t03-blocking", "a real blocking incident: diagnose, fix with RCSI, and measure the waits")]


def report(key: str, table: list[list[str]], expected: list[list[str]], wild: bool = True) -> list[str]:
    print(format_table(table))
    return (diff_wild if wild else diff)(expected, table)


def run_sqlserver(connect, steps: list[Step], setup: bool, sleep=time.sleep, clock=time.monotonic) -> int:
    if setup:
        master = open_session(connect, "master")
        master.run_file(SQL_DIR / "00-create-database.sql")
        master.close()
        eng = open_session(connect)
        for f in ("01-schema-and-data.sql", "10-tune-tools.sql"):
            eng.run_file(SQL_DIR / f)
        eng.close()
        print(f"setup: {DB} with episode 4's 200,000 orders and the Tune schema (wait snapshots)")
    failures = 0
    for step in steps:
        print(f"\n{step.key}: {step.title}")
        problems: list[str] = []
        try:
            if step.key == "t03-blocking":
                blocking, waits = blocking_phase(connect, sleep, clock)
                print("\nthe incident:")
                problems += report(step.key, blocking, read_csv(EXPECTED_DIR / "t03-blocking.csv"))
                print("\nthe waits (Tune.usp_WaitDelta):")
                problems += [f"waits: {p}" for p in report(step.key, waits, read_csv(EXPECTED_DIR / "t04-wait-delta.csv"))]
            else:
                eng = open_session(connect)
                try:
                    for f in step.before:
                        run_one(eng, f)
                        print(f"  ran {f}")
                    res = run_one(eng, step.key)
                finally:
                    eng.close()
                if res.columns is None:
                    problems.append("no result set")
                else:
                    problems += report(step.key, to_table(res.columns, res.rows), read_csv(EXPECTED_DIR / f"{step.key}.csv"))
        except Exception as e:  # noqa: BLE001 - an unexpected error fails the step
            problems.append(f"unexpected error: {str(e)[:300]}")
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(steps) - failures}/{len(steps)} steps behaved as expected on sqlserver")
    return 1 if failures else 0


def reset(connect) -> int:
    try:
        eng = open_session(connect)
    except RuntimeError as e:
        print(f"reset: nothing to do ({str(e)[:120]})")
        return 0
    try:
        res = eng.run_script(sql_text("t05-cleanup"))
    finally:
        eng.close()
    if res.errors:
        print("reset FAILED: " + res.errors[0][:200])
        return 1
    print("reset: READ_COMMITTED_SNAPSHOT off, Tune objects dropped (the 200,000 orders stay)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: create the database, load the data, create the Tune objects")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: run t05-cleanup.sql and stop")
    ap.add_argument("--step", action="append", help="run only these steps (repeatable)")
    a = ap.parse_args(argv)

    steps = [s for s in STEPS if not a.step or s.key in a.step]
    if a.step and len(steps) != len(a.step):
        ap.error(f"unknown step; choose from {[s.key for s in STEPS]}")
    if a.engine == "duckdb":
        return run_local()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")

    def connect():
        from mssql_python import connect as mssql_connect
        return mssql_connect(conn_str, autocommit=True)

    if a.reset_only:
        return reset(connect)
    return run_sqlserver(connect, steps, a.setup)


if __name__ == "__main__":
    sys.exit(main())
