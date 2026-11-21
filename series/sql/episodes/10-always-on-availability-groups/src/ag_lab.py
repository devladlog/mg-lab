"""Always On availability group lab runner (DEVLADLOG SQL #10): a real two-replica group (CON-SQL01 primary, CON-SQL02
secondary, synchronous commit, automatic seeding) on a Windows failover cluster, a gotcha with the readable
secondary, the redo lag, a planned failover and failback with a stopwatch, and an optional listener.

Needs TWO connections: SQL_CONNECTION_STRING (CON-SQL01) and SQL_CONNECTION_STRING_SQL02 (CON-SQL02), both sysadmin.
The cluster and Always On are prepared first with src/ps/Prepare-AgCluster.ps1 (demo.md).

* ``sqlserver`` - the demo. Ten steps, each compared with expected/ (``*`` = any value). Steps that depend on
  asynchronous work (seeding, redo, role change) re-run their last query until it matches or its timeout is up, and
  print how long that took.
* ``duckdb``    - the local check: the order counts of the drill (write on the primary, read on the secondary, write
  on the new primary) on a model in which a replica is a database; the AG itself needs SQL Server and a cluster.

    python src/ag_lab.py                                         # duckdb
    python src/ag_lab.py --engine sqlserver --setup              # reset, then all steps
    python src/ag_lab.py --engine sqlserver --step a15-listener  # the optional listener
    python src/ag_lab.py --engine sqlserver --health             # failover readiness verdicts from the primary
    python src/ag_lab.py --engine sqlserver --watch              # time an AUTOMATIC failover (stop the primary's service)
    python src/ag_lab.py --engine sqlserver --reset-only         # tear-down: group, database, endpoints, logins
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
import ag_health  # noqa: E402
from labdb import (DuckDBEngine, ScriptResult, SqlServerEngine, format_table, read_csv,  # noqa: E402
                   split_batches, to_table)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
AG, DB = "ag_contoso", "ContosoBikesAG"
NODES = {"sql01": "CON-SQL01", "sql02": "CON-SQL02"}
ENV = {"sql01": "SQL_CONNECTION_STRING", "sql02": "SQL_CONNECTION_STRING_SQL02"}
POLL_SECONDS = 1.0
FAILOVER_LIMIT_SECONDS = 60.0     # our own target for a planned failover in this lab, not a Microsoft figure
WATCH_LIMIT_SECONDS = 120.0       # same for the automatic failover seen by the poller


@dataclass
class Action:
    node: str                      # "sql01" or "sql02"
    file: str                      # src/sql/<file>.sql
    db: str = "master"             # the database the connection is in before the file runs


@dataclass
class Step:
    key: str
    title: str
    actions: list[Action]
    expected: str | None = None                       # expected/<expected or key>.csv
    result: bool = True                               # compare the last action's result set
    merge: bool = False                               # run every action once, concatenate their result rows
    poll: float | None = None                         # re-run the last action up to this many seconds until it matches
    limit: float | None = None                        # the whole step must finish within this many seconds
    checks: list[str] = field(default_factory=lambda: ["error: none"])
    same: list[str] = field(default_factory=list)     # columns that must have the same value in every row
    health: bool = False                              # print ag_health verdicts for the result rows
    optional: bool = False                            # only runs when asked for with --step


STEPS = [
    Step("a02-prereqs", "Always On enabled, same collation and version, quorum normal",
         [Action("sql01", "a02-prereqs"), Action("sql02", "a02-prereqs")], merge=True, same=["Collation", "ProductVersion"]),
    Step("a03-endpoints", "the mirroring endpoint on each replica, and the peer's login",
         [Action("sql01", "a03-endpoint-sql01"), Action("sql02", "a03-endpoint-sql02")], expected="a03-endpoints", merge=True),
    Step("a04-database", "ContosoBikesAG: FULL recovery, episode 5's data, one full backup",
         [Action("sql01", "a04-create-database"), Action("sql01", "01-schema-and-data", DB), Action("sql01", "a04-backup")]),
    Step("a05-create-ag", "create the group, join the secondary, automatic seeding until SYNCHRONIZED",
         [Action("sql01", "a05-create-ag"), Action("sql02", "a06-join-ag"), Action("sql01", "a07-health")], poll=120.0, health=True),
    Step("a08-secondary-read-fails", "gotcha: reading the secondary with ALLOW_CONNECTIONS = NO",
         [Action("sql02", "a08-secondary-read-fails")], result=False, checks=["error: contains: not accessible for queries"]),
    Step("a09-allow-read", "ALLOW_CONNECTIONS = ALL on both replicas, then read the secondary",
         [Action("sql01", "a09-allow-read"), Action("sql02", "a10-secondary-read")], poll=30.0),
    Step("a11-write-and-read", "order 1009 on the primary, read on the secondary (redo lag)",
         [Action("sql01", "d01-order-1009", DB), Action("sql02", "a10-secondary-read")], poll=30.0),
    Step("a12-failover", "planned failover to CON-SQL02 (timed)",
         [Action("sql02", "a12-failover"), Action("sql02", "a07-health")], poll=FAILOVER_LIMIT_SECONDS,
         limit=FAILOVER_LIMIT_SECONDS, health=True),
    Step("a13-write-on-new-primary", "order 1010 on the new primary, read on the old one",
         [Action("sql02", "d02-order-1010", DB), Action("sql01", "a10-secondary-read")], poll=30.0),
    Step("a14-failback", "planned failover back to CON-SQL01 (timed)",
         [Action("sql01", "a12-failover"), Action("sql01", "a07-health")], expected="a05-create-ag",
         poll=FAILOVER_LIMIT_SECONDS, limit=FAILOVER_LIMIT_SECONDS, health=True),
    Step("a15-listener", "optional: a listener with a static IP", [Action("sql01", "a15-listener")], optional=True),
]


def sql_text(name: str) -> str:
    return (SQL_DIR / (name if name.endswith(".sql") else f"{name}.sql")).read_text(encoding="utf-8")


def evaluate(check: str, errors: list[str]) -> str | None:
    kind, _, arg = check.partition(":")
    arg = arg.strip()
    if kind == "error" and arg == "none":
        return None if not errors else f"unexpected error: {errors[0][:200]}"
    if kind == "error" and arg.startswith("contains:"):
        needle = arg.split(":", 1)[1].strip().lower()
        if not errors:
            return "expected an error, none was raised"
        return None if any(needle in e.lower() for e in errors) else f"error does not mention {needle!r}: {errors[0][:200]}"
    raise ValueError(f"unknown check: {check}")


def diff_wild(expected: list[list[str]], actual: list[list[str]]) -> list[str]:
    """Like labdb.diff, but ``*`` in expected/ matches any value (times, sizes, versions)."""
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
def run_local() -> int:
    """Replicas as databases: 'seeding' copies the primary's tables, a failover swaps the roles. Checks the data side
    of the drill: 8 -> 9 (write on the primary) -> secondary catches up -> 10 (write on the new primary)."""
    eng = DuckDBEngine(schemas=())
    problems: list[str] = []
    role = {"sql01": "PRIMARY", "sql02": "SECONDARY"}
    dbs = {"sql01": "Replica1", "sql02": "Replica2"}

    def primary() -> str:
        return next(n for n, r in role.items() if r == "PRIMARY")

    def secondary() -> str:
        return next(n for n, r in role.items() if r == "SECONDARY")

    def orders(node: str) -> int:
        return eng.query(f"SELECT COUNT(*) FROM {dbs[node]}.Sales.Orders")[1][0][0]

    def seed_secondary() -> None:      # the secondary is "redone" up to the primary
        src, dst = dbs[primary()], dbs[secondary()]
        tables = ("Customers", "Products", "Orders", "OrderLines")      # parents first
        try:
            for t in reversed(tables):
                eng.con.execute(f"DELETE FROM {dst}.Sales.{t}")
        except Exception:  # noqa: BLE001 - the very first copy: the secondary has no tables yet
            pass
        for t in tables:
            if eng.query(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_catalog = '{dst}' AND table_name = '{t}'")[1][0][0]:
                eng.con.execute(f"INSERT INTO {dst}.Sales.{t} SELECT * FROM {src}.Sales.{t}")
            else:
                eng.con.execute(f"CREATE TABLE {dst}.Sales.{t} AS SELECT * FROM {src}.Sales.{t}")

    def run_on_primary(sql_file: str) -> None:
        eng.con.execute(f"USE {dbs[primary()]}")
        eng.run_file(SQL_DIR / sql_file)

    def check(key: str, got: list[tuple[str, int | str]]) -> None:
        table = [["Item", "Result"]] + [[k, str(v)] for k, v in got]
        want = [r for r in read_csv(EXPECTED_DIR / f"{key}.csv")[1:] if r[0] in {k for k, _ in got}]
        print(f"\n{key}"); print(format_table(table))
        if want != table[1:]:
            problems.append(f"{key}: expected {want}, got {table[1:]}")

    try:
        for db in dbs.values():
            eng.con.execute(f"ATTACH ':memory:' AS {db}")
            eng.con.execute(f"CREATE SCHEMA {db}.Sales")
        eng.con.execute(f"USE {dbs['sql01']}")
        eng.run_file(SQL_DIR / "01-schema-and-data.sql")
        seed_secondary()
        print("model: episode 5's seed on the primary; 'seeding' and 'redo' = copy the tables to the secondary")
        check("a04-database", [("Orders", orders("sql01"))])
        check("a09-allow-read", [("Orders on this replica", orders(secondary())), ("Role of this replica", role[secondary()])])
        run_on_primary("d01-order-1009.sql")
        seed_secondary()
        check("a11-write-and-read", [("Orders on this replica", orders(secondary())), ("Role of this replica", role[secondary()])])
        role["sql01"], role["sql02"] = "SECONDARY", "PRIMARY"          # a12-failover
        run_on_primary("d02-order-1010.sql")
        seed_secondary()
        check("a13-write-on-new-primary", [("Orders on this replica", orders(secondary())), ("Role of this replica", role[secondary()])])
        role["sql01"], role["sql02"] = "PRIMARY", "SECONDARY"          # a14-failback
        print(f"\nafter the failback: primary {primary()} has {orders(primary())} orders, secondary {secondary()} has {orders(secondary())}")
        if (orders("sql01"), orders("sql02")) != (10, 10):
            problems.append("failback: both replicas should hold 10 orders")
    finally:
        eng.close()
    print("\n" + ("local checks: the order counts of the drill match expected/ on duckdb (the group, seeding, failover and the error need SQL Server)"
                  if not problems else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
class Cluster:
    """One lazily opened connection per replica. ``connect(node)`` returns a DB-API connection."""

    def __init__(self, connect) -> None:
        self._connect, self._engines = connect, {}

    def engine(self, node: str) -> SqlServerEngine:
        if node not in self._engines:
            self._engines[node] = SqlServerEngine(connection=self._connect(node))
        return self._engines[node]

    def close(self) -> None:
        for e in self._engines.values():
            try:
                e.close()
            except Exception:  # noqa: BLE001 - closing a connection to a stopped replica may fail
                pass
        self._engines.clear()


def run_action(cluster: Cluster, a: Action) -> ScriptResult:
    eng = cluster.engine(a.node)
    res = eng.run_script(f"USE {a.db};")
    if res.errors:
        return res
    return eng.run_script(sql_text(a.file))


def merged(results: list[ScriptResult]) -> ScriptResult:
    out = ScriptResult()
    for r in results:
        out.errors += r.errors
        if r.columns is not None:
            out.columns = out.columns or r.columns
            out.rows += r.rows
    return out


def run_step(cluster: Cluster, step: Step, sleep=time.sleep, clock=time.monotonic) -> tuple[list[str], ScriptResult | None, float]:
    """(problems, last result, seconds). All but the last action run once; the last one is re-run while it does not match."""
    problems: list[str] = []
    t0 = clock()
    if step.merge:
        results = [run_action(cluster, a) for a in step.actions]
        res = merged(results)
        errors = res.errors
    else:
        pre = [run_action(cluster, a) for a in step.actions[:-1]]
        res = run_action(cluster, step.actions[-1])
        errors = [e for r in pre for e in r.errors]
        if step.poll and step.result:
            want = read_csv(EXPECTED_DIR / f"{step.expected or step.key}.csv")
            tries = 1
            while clock() - t0 < step.poll and (res.errors or res.columns is None or
                                                diff_wild(want, to_table(res.columns, res.rows))):
                sleep(POLL_SECONDS)
                res = run_action(cluster, step.actions[-1])
                tries += 1
            print(f"  matched after {clock() - t0:.1f} s ({tries} {'run' if tries == 1 else 'runs'} of the last query)"
                  if not res.errors and res.columns and not diff_wild(want, to_table(res.columns, res.rows))
                  else f"  gave up after {clock() - t0:.1f} s ({tries} runs of the last query)")
        errors += res.errors
    seconds = clock() - t0
    problems += [f"{c}: {why}" for c in step.checks if (why := evaluate(c, errors))]
    return problems, res, seconds


def compare(step: Step, res: ScriptResult | None) -> tuple[list[str], list[list[str]] | None]:
    if not step.result:
        return [], None
    if res is None or res.columns is None:
        return ["no result set"], None
    table = to_table(res.columns, res.rows)
    problems = diff_wild(read_csv(EXPECTED_DIR / f"{step.expected or step.key}.csv"), table)
    for col in step.same:
        values = {r[table[0].index(col)] for r in table[1:]}
        if len(values) > 1:
            problems.append(f"{col} differs between the replicas: {sorted(values)}")
    return problems, table


def run_sqlserver(connect, steps: list[Step], setup: bool, sleep=time.sleep, clock=time.monotonic) -> int:
    cluster = Cluster(connect)
    try:
        if setup:
            for node in ("sql02", "sql01"):
                res = run_action(cluster, Action(node, "a00-reset"))
                if res.errors:
                    raise RuntimeError(f"reset on {NODES[node]}: {res.errors[0]}")
            print(f"setup: group {AG} and database {DB} removed from both replicas (endpoints and logins stay)")
        failures = 0
        for step in steps:
            print(f"\n{step.key}: {step.title}")
            try:
                problems, res, seconds = run_step(cluster, step, sleep, clock)
                for c in step.checks:
                    print(f"  check {c:<52} {'OK' if not any(p.startswith(c + ':') for p in problems) else 'FAILED'}")
                if step.limit is not None:
                    print(f"  step took {seconds:.1f} s (limit {step.limit:.0f} s)")
                    if seconds > step.limit:
                        problems.append(f"took {seconds:.1f} s, limit {step.limit:.0f} s")
                more, table = compare(step, res)
                problems += more
                if table:
                    print(format_table(table))
                    if step.health and res is not None and res.rows:
                        print("  " + ag_health.render(ag_health.assess(res.rows)).replace("\n", "\n  "))
            except Exception as e:  # noqa: BLE001 - an unexpected error fails the step
                problems = [f"unexpected error: {str(e)[:300]}"]
            print("  => OK" if not problems else "  => " + "; ".join(problems))
            failures += bool(problems)
        print(f"\n{len(steps) - failures}/{len(steps)} steps behaved as expected on sqlserver")
        return 1 if failures else 0
    finally:
        cluster.close()


def reset(connect) -> int:
    cluster = Cluster(connect)
    try:
        for node in ("sql02", "sql01"):
            res = run_action(cluster, Action(node, "a00-reset"))
            if res.errors:
                print(f"reset FAILED on {NODES[node]}: {res.errors[0][:200]}")
                return 1
        for node, f in (("sql01", "a14-teardown-sql01"), ("sql02", "a14-teardown-sql02")):
            res = run_action(cluster, Action(node, f))
            if res.errors:
                print(f"reset FAILED on {NODES[node]}: {res.errors[0][:200]}")
                return 1
        print("reset: group, database, msdb history, endpoints and peer logins removed from both replicas "
              "(the backup file and the cluster stay: demo.md, tear-down)")
        return 0
    finally:
        cluster.close()


def health(connect) -> int:
    """Failover readiness, asked of whichever replica is the primary."""
    cluster = Cluster(connect)
    try:
        for node in ("sql01", "sql02"):
            res = run_action(cluster, Action(node, "a16-role"))
            if not res.errors and res.rows and res.rows[0][0] == "PRIMARY":
                h = run_action(cluster, Action(node, "a07-health"))
                if h.errors or not h.rows:
                    print("health FAILED: " + (h.errors[0][:200] if h.errors else "no rows"))
                    return 1
                v = ag_health.assess(h.rows)
                print(f"primary: {NODES[node]}")
                print(ag_health.render(v))
                return 0 if ag_health.summary(v).startswith("FAILOVER READY") else 1
        print("health: no replica reports PRIMARY (group not created, or failing over)")
        return 1
    finally:
        cluster.close()


@dataclass
class WatchResult:
    old_primary: str
    new_primary: str | None
    seconds: float | None


def role_of(cluster_connect, node: str) -> str | None:
    """The replica's role, or None when it cannot be reached (a fresh connection each time: a stopped service
    drops the old one)."""
    try:
        eng = SqlServerEngine(connection=cluster_connect(node))
    except Exception:  # noqa: BLE001
        return None
    try:
        res = eng.run_script(sql_text("a16-role"))
        return res.rows[0][0] if not res.errors and res.rows else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            eng.close()
        except Exception:  # noqa: BLE001
            pass


def watch(connect, limit: float = WATCH_LIMIT_SECONDS, sleep=time.sleep, clock=time.monotonic, out=print) -> WatchResult | None:
    """Times an automatic failover as a client polling both replicas sees it: from the first poll in which the old
    primary no longer says PRIMARY (or is unreachable) to the first poll in which the other replica says PRIMARY."""
    old = None
    for _ in range(30):
        for node in ("sql01", "sql02"):
            if role_of(connect, node) == "PRIMARY":
                old = node
                break
        if old:
            break
        sleep(POLL_SECONDS)
    if old is None:
        out("watch: no replica reports PRIMARY")
        return None
    other = "sql02" if old == "sql01" else "sql01"
    out(f"watch: primary is {NODES[old]}. Stop its SQL Server service now (src/ps/Stop-AgPrimary.ps1 -Node {NODES[old]}); polling every second.")
    t_loss = None
    deadline = None
    while True:
        now = clock()
        if deadline is not None and now > deadline:
            out(f"watch: no failover within {limit:.0f} s of the first failed poll")
            return WatchResult(NODES[old], None, None)
        r_old, r_other = role_of(connect, old), role_of(connect, other)
        now = clock()
        if t_loss is None and r_old != "PRIMARY":
            t_loss = now
            deadline = now + limit
            out(f"watch: {NODES[old]} no longer PRIMARY (role: {r_old or 'unreachable'}); stopwatch running")
        if t_loss is not None and r_other == "PRIMARY":
            secs = now - t_loss
            out(f"watch: {NODES[other]} is PRIMARY after {secs:.1f} s (limit {limit:.0f} s, our own target)")
            return WatchResult(NODES[old], NODES[other], secs)
        sleep(POLL_SECONDS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: remove the group and database from both replicas first")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: tear-down of the SQL side (a00, a14) and stop")
    ap.add_argument("--health", action="store_true", help="sqlserver: failover readiness verdicts from the primary")
    ap.add_argument("--watch", action="store_true", help="sqlserver: time an automatic failover (you stop the primary's service)")
    ap.add_argument("--step", action="append", help="run only these steps (repeatable; they build on each other)")
    a = ap.parse_args(argv)

    steps = [s for s in STEPS if (s.key in a.step if a.step else not s.optional)]
    if a.step and len(steps) != len(a.step):
        ap.error(f"unknown step; choose from {[s.key for s in STEPS]}")
    if a.engine == "duckdb":
        return run_local()
    conns = {n: os.environ.get(v) for n, v in ENV.items()}
    missing = [ENV[n] for n, c in conns.items() if not c]
    if missing:
        ap.error("set " + " and ".join(missing) + " for --engine sqlserver")

    def connect(node: str):
        from mssql_python import connect as mssql_connect
        return mssql_connect(conns[node], autocommit=True)

    if a.reset_only:
        return reset(connect)
    if a.health:
        return health(connect)
    if a.watch:
        r = watch(connect)
        return 0 if r and r.seconds is not None and r.seconds <= WATCH_LIMIT_SECONDS else 1
    return run_sqlserver(connect, steps, a.setup)


if __name__ == "__main__":
    sys.exit(main())
