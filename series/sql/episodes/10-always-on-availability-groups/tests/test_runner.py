"""The SQL Server path of ag_lab.py against a fake two-replica cluster: roles swap on ALTER AVAILABILITY GROUP ... FAILOVER,
the secondary refuses reads until ALLOW_CONNECTIONS = ALL (error 976), a write shows up on the secondary only after a few
polls (redo lag), seeding takes a few polls, and a stopped replica is unreachable. What SQL Server and the cluster really
do is checked by the same code during the recording."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ag_lab as lab  # noqa: E402
import labdb  # noqa: E402

ERR_976 = ("The target database, 'ContosoBikesAG', is participating in an availability group and is currently not "
           "accessible for queries. Either data movement is suspended or the availability replica isn't enabled for read access. (976)")


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, s):
        self.now += s


class FakeCursor:
    def __init__(self, server, node):
        self.server, self.node, self.sets, self.description, self._rows = server, node, [], None, []

    def execute(self, sql):
        self.server.log.append((self.node, sql))
        self.sets = self.server.answer(self.node, sql)
        self._load()

    def _load(self):
        if self.sets:
            cols, self._rows = self.sets.pop(0)
            self.description = [(c,) for c in cols]
        else:
            self.description, self._rows = None, []

    def fetchall(self):
        return self._rows

    def nextset(self):
        if not self.sets:
            return None
        self._load()
        return True

    def close(self):
        pass


class Conn:
    def __init__(self, server, node):
        self.server, self.node = server, node

    def cursor(self):
        return FakeCursor(self.server, self.node)

    def close(self):
        pass


def csv_rows(name):
    t = labdb.read_csv(ROOT / "expected" / f"{name}.csv")
    return t[0], [tuple(r) for r in t[1:]]


class FakeCluster:
    def __init__(self, lag=3, seed_polls=3, failover_polls=3, never_synchronized=False, readable=False):
        self.log, self.lag, self.seed_polls, self.failover_polls = [], lag, seed_polls, failover_polls
        self.never_synchronized = never_synchronized
        self.roles = {"sql01": "PRIMARY", "sql02": "SECONDARY"}
        self.readable, self.orders, self.visible, self.pending = readable, 8, {"sql01": 8, "sql02": 8}, {}
        self.settling = 0
        self.batches = {}
        for f in sorted(lab.SQL_DIR.glob("*.sql")):
            for b in labdb.split_batches(f.read_text(encoding="utf-8")):
                self.batches.setdefault(b, []).append(f.stem)

    def connect(self, node):
        return Conn(self, node)

    def which(self, sql):
        code = "\n".join(l for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")).strip()
        if code == "USE master;":
            return None
        files = self.batches.get(sql.strip(), [])
        return files[0] if files else None

    def health_rows(self):
        synced = not self.never_synchronized and self.settling <= 0
        name = "a05-create-ag" if self.roles["sql01"] == "PRIMARY" else "a12-failover"
        cols, rows = csv_rows(name)
        rows = [tuple(("0" if v == "*" else v) for v in r) for r in rows]
        if not synced:
            rows = [r[:5] + ("SYNCHRONIZING", "PARTIALLY_HEALTHY") + r[7:] if r[1] == "SECONDARY" else r for r in rows]
        self.settling -= 1
        return [(cols, rows)]

    def answer(self, node, sql):
        f = self.which(sql)
        s = sql.strip()
        if f is None:
            return []
        if f == "a02-prereqs":
            c, rows = csv_rows("a02-prereqs")
            return [(c, [tuple("x" if v == "*" else v for v in r) for r in rows if r[0] == lab.NODES[node]])]
        if f.startswith("a03-endpoint"):
            c, rows = csv_rows("a03-endpoints")
            return [(c, [r for r in rows if r[0] == lab.NODES[node]])]
        if f == "a04-backup" and s.startswith("SELECT"):
            c, rows = csv_rows("a04-database")
            return [(c, rows)]
        if f == "a05-create-ag":
            self.settling = self.seed_polls
            return []
        if f == "a07-health":
            return self.health_rows()
        if f == "a08-secondary-read-fails" or (f == "a10-secondary-read" and not self.readable):
            raise RuntimeError(ERR_976)
        if f == "a09-allow-read":
            self.readable = True
            return []
        if f == "a10-secondary-read":
            if node in self.pending:
                count, left = self.pending[node]
                if left <= 0:
                    self.visible[node] = count
                    del self.pending[node]
                else:
                    self.pending[node] = (count, left - 1)
            return [(["Item", "Result"], [("Orders on this replica", str(self.visible[node])), ("Role of this replica", self.roles[node])])]
        if f.startswith("d0") and "INSERT INTO Sales.Orders" in s:
            self.orders += 1
            primary = next(n for n, r in self.roles.items() if r == "PRIMARY")
            other = "sql02" if primary == "sql01" else "sql01"
            self.visible[primary] = self.orders
            self.pending[other] = (self.orders, self.lag)
            return []
        if f == "a12-failover":
            self.roles = {n: ("PRIMARY" if n == node else "SECONDARY") for n in self.roles}
            self.settling = self.failover_polls
            return []
        if f == "a16-role":
            return [(["Role"], [(self.roles[node],)])]
        return []


def run(server, steps=None, setup=True, t=None):
    t = t or FakeTime()
    return lab.run_sqlserver(server.connect, steps or [s for s in lab.STEPS if not s.optional], setup, t.sleep, t.clock), t


def step(key):
    return [s for s in lab.STEPS if s.key == key]


def test_all_default_steps_pass_when_the_cluster_behaves(capsys):
    code, _ = run(FakeCluster())
    out = capsys.readouterr().out
    assert code == 0, out
    assert "10/10 steps behaved as expected on sqlserver" in out
    assert "check error: contains: not accessible for queries" in out
    assert "FAILOVER READY, NO DATA LOSS (automatic)" in out


def test_setup_resets_the_secondary_first_then_the_primary(capsys):
    server = FakeCluster()
    run(server)
    resets = [n for n, sql in server.log if sql.strip().startswith("IF EXISTS (SELECT 1 FROM sys.availability_groups")]
    assert resets == ["sql02", "sql01"]


def test_actions_run_on_the_nodes_the_story_says(capsys):
    server = FakeCluster()
    run(server)
    ran = [(n, server.which(sql)) for n, sql in server.log if server.which(sql)]
    firsts = {}
    for n, f in ran:
        firsts.setdefault(f, n)
    assert firsts["a05-create-ag"] == "sql01" and firsts["a06-join-ag"] == "sql02" and firsts["a08-secondary-read-fails"] == "sql02"
    assert [n for n, f in ran if f == "a12-failover"] == ["sql02", "sql01"]         # failover to sql02, failback to sql01
    assert [n for n, f in ran if f in ("d01-order-1009", "d02-order-1010")][:2] == ["sql01", "sql02"]


def test_data_files_run_in_the_lab_database(capsys):
    server = FakeCluster()
    run(server)
    i = next(k for k, (n, sql) in enumerate(server.log) if server.which(sql) == "d01-order-1009")
    assert server.log[i - 1] == ("sql01", "USE ContosoBikesAG;")


def test_reading_the_secondary_must_fail_with_976(capsys):
    code, _ = run(FakeCluster(), step("a08-secondary-read-fails"), setup=False)
    assert code == 0 and re.search(r"check error: contains: not accessible for queries\s+OK", capsys.readouterr().out)


def test_a_read_that_works_when_it_should_fail_is_a_failure(capsys):
    class Lenient(FakeCluster):
        def answer(self, node, sql):
            return [] if self.which(sql) == "a08-secondary-read-fails" else super().answer(node, sql)
    code, _ = run(Lenient(), step("a08-secondary-read-fails"), setup=False)
    assert code == 1 and "expected an error, none was raised" in capsys.readouterr().out


def test_a_different_error_is_a_failure(capsys):
    class Other(FakeCluster):
        def answer(self, node, sql):
            if self.which(sql) == "a08-secondary-read-fails":
                raise RuntimeError("Login failed for user. (18456)")
            return super().answer(node, sql)
    code, _ = run(Other(), step("a08-secondary-read-fails"), setup=False)
    assert code == 1 and "does not mention" in capsys.readouterr().out


def test_redo_lag_is_polled_and_reported(capsys):
    server = FakeCluster(lag=4, readable=True)
    code, t = run(server, step("a11-write-and-read"), setup=False)
    out = capsys.readouterr().out
    assert code == 0 and "matched after" in out and "5 runs of the last query" in out
    assert t.now == 4.0


def test_a_secondary_that_never_catches_up_fails_after_the_timeout(capsys):
    code, t = run(FakeCluster(lag=10_000, readable=True), step("a11-write-and-read"), setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "gave up after" in out and "row 1: expected" in out and t.now >= 30


def test_seeding_is_polled_until_synchronized(capsys):
    code, t = run(FakeCluster(seed_polls=5), step("a05-create-ag"), setup=False)
    out = capsys.readouterr().out
    assert code == 0 and "matched after" in out and t.now == 5.0


def test_a_group_that_never_synchronizes_fails_and_the_verdict_says_why(capsys):
    code, _ = run(FakeCluster(never_synchronized=True), step("a05-create-ag"), setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "gave up after" in out


def test_planned_failover_swaps_the_roles_and_prints_the_stopwatch(capsys):
    server = FakeCluster(readable=True)
    code, t = run(server, step("a12-failover"), setup=False)
    out = capsys.readouterr().out
    assert code == 0 and "step took 3.0 s (limit 60 s)" in out and server.roles["sql02"] == "PRIMARY"


def test_a_failover_that_takes_too_long_fails(capsys):
    code, _ = run(FakeCluster(failover_polls=1000, readable=True), step("a12-failover"), setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "gave up after" in out and "limit 60 s" in out


def test_the_merged_prereq_table_has_both_nodes_and_checks_collation(capsys):
    code, _ = run(FakeCluster(), step("a02-prereqs"), setup=False)
    out = capsys.readouterr().out
    assert code == 0 and "CON-SQL01" in out and "CON-SQL02" in out

    class Different(FakeCluster):
        def answer(self, node, sql):
            r = super().answer(node, sql)
            if self.which(sql) == "a02-prereqs":
                c, rows = r[0]
                return [(c, [(row[0], row[1], "Latin1_General_CI_AS" if node == "sql02" else "SQL_Latin1_General_CP1_CI_AS") + tuple(row[3:]) for row in rows])]
            return r
    code, _ = run(Different(), step("a02-prereqs"), setup=False)
    assert code == 1 and "Collation differs between the replicas" in capsys.readouterr().out


def test_an_unexpected_exception_fails_only_its_step(capsys):
    class Boom(FakeCluster):
        def answer(self, node, sql):
            if self.which(sql) == "a04-backup":
                raise ConnectionError("connection lost")
            return super().answer(node, sql)
    code, _ = run(Boom(), [s for s in lab.STEPS if s.key in ("a04-database", "a08-secondary-read-fails")], setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "1/2 steps" in out


def test_reset_only_runs_reset_then_teardown_on_both(monkeypatch, capsys):
    server = FakeCluster()
    assert lab.reset(server.connect) == 0
    files = [(n, server.which(sql)) for n, sql in server.log if server.which(sql)]
    nodes = [n for k, (n, _) in enumerate(files) if k == 0 or n != files[k - 1][0]]
    assert nodes == ["sql02", "sql01", "sql02"]                  # reset secondary, reset primary + its teardown, then the other teardown
    assert files[0] == ("sql02", "a00-reset") and ("sql01", "a00-reset") in files
    assert "reset:" in capsys.readouterr().out


def test_health_asks_the_primary_and_exits_by_the_verdict(capsys):
    server = FakeCluster(readable=True)
    assert lab.health(server.connect) == 0
    out = capsys.readouterr().out
    assert "primary: CON-SQL01" in out and "FAILOVER READY" in out
    assert lab.health(FakeCluster(never_synchronized=True).connect) == 1
    server = FakeCluster()
    server.roles = {"sql01": "RESOLVING", "sql02": "RESOLVING"}
    assert lab.health(server.connect) == 1 and "no replica reports PRIMARY" in capsys.readouterr().out


# ---------------------------------------------------------------- --watch
class Timeline:
    """plan(node, t) -> 'PRIMARY' | 'SECONDARY' | ... | None (unreachable), driven by the fake time."""
    def __init__(self, t, plan):
        self.t, self.plan, self.log = t, plan, []

    def __call__(self, node):
        if self.plan(node, self.t.now) is None:
            raise ConnectionError("server is not reachable")
        return Conn(self, node)

    def answer(self, node, sql):
        return [(["Role"], [(self.plan(node, self.t.now),)])]


def watch_with(plan, limit=120.0):
    t = FakeTime()
    tl = Timeline(t, plan)
    out = []
    result = lab.watch(tl, limit, t.sleep, t.clock, out.append)
    return result, out


def test_watch_times_the_gap_between_the_first_failed_poll_and_the_new_primary():
    def plan(node, now):
        if node == "sql01":
            return "PRIMARY" if now < 5 else None
        return "PRIMARY" if now >= 17 else "SECONDARY"
    result, out = watch_with(plan)
    assert result.old_primary == "CON-SQL01" and result.new_primary == "CON-SQL02"
    assert result.seconds == 12.0
    assert any("stopwatch running" in line for line in out) and "after 12.0 s" in out[-1]


def test_watch_sees_a_service_that_stays_up_but_demotes_itself():
    def plan(node, now):
        if node == "sql01":
            return "PRIMARY" if now < 3 else "RESOLVING"
        return "PRIMARY" if now >= 6 else "SECONDARY"
    result, out = watch_with(plan)
    assert result.seconds == 3.0 and "role: RESOLVING" in "\n".join(out)


def test_watch_gives_up_when_nothing_takes_over():
    result, out = watch_with(lambda node, now: ("PRIMARY" if now < 2 else None) if node == "sql01" else "SECONDARY", limit=20)
    assert result.new_primary is None and result.seconds is None and "no failover within 20 s" in out[-1]


def test_watch_reports_when_there_is_no_primary_at_all():
    result, out = watch_with(lambda node, now: "SECONDARY")
    assert result is None and "no replica reports PRIMARY" in out[-1]


def test_watch_works_when_the_primary_is_sql02():
    def plan(node, now):
        if node == "sql02":
            return "PRIMARY" if now < 2 else None
        return "PRIMARY" if now >= 8 else "SECONDARY"
    result, _ = watch_with(plan)
    assert result.old_primary == "CON-SQL02" and result.new_primary == "CON-SQL01" and result.seconds == 6.0
