"""The SQL Server path of perf_lab.py against a fake server that has real threads: the writer's open transaction blocks
the reader until it rolls back (unless READ_COMMITTED_SNAPSHOT is on), the diagnosing connection sees the wait, and
ALTER DATABASE ... READ_COMMITTED_SNAPSHOT refuses to run while another connection is open. What SQL Server really
does is checked by the same code during the recording on CON-SQL01."""
from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import perf_lab as lab  # noqa: E402

def code(sql):
    """The batch without comment lines (the files start with comments; the checks below look at the code)."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip()


FAST = lambda s: time.sleep(0.005)      # noqa: E731


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.sets, self.description, self._rows = conn, [], None, []

    def execute(self, sql):
        self.conn.server.log.append(sql)
        self.sets = self.conn.server.answer(self.conn, sql)
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


class FakeConnection:
    def __init__(self, server):
        self.server = server
        with server.lock:
            server.next_spid += 1
            server.open += 1
            self.spid, self.db = server.next_spid, "master"

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        with self.server.lock:
            self.server.open -= 1


class FakeServer:
    def __init__(self, never_block=False, rcsi_ignored=False, lock_ms=5000, missing_db=False, replace=None):
        self.log, self.lock = [], threading.Lock()
        self.next_spid, self.open = 50, 0
        self.locked_by, self.waiting, self.rcsi = None, None, False
        self.release = threading.Event()
        self.never_block, self.rcsi_ignored, self.lock_ms, self.missing_db = never_block, rcsi_ignored, lock_ms, missing_db
        self.replace = replace or {}                      # step key -> function(table) -> table
        self.snapshots = []
        self.batches = {code(lab.split_batches(lab.sql_text(k))[-1]): k for k in ("t01-config-review", "t02-top-queries")}
        self.diag_text = code(lab.split_batches(lab.sql_text("t03c-diagnose"))[0])
        self.reader_text = code(lab.split_batches(lab.sql_text("t03b-reader"))[0])

    def connect(self):
        return FakeConnection(self)

    def csv_answer(self, key, fill):
        table = labdb.read_csv(ROOT / "expected" / f"{key}.csv")
        rows = [tuple(fill if c == "*" else c for c in r) for r in table[1:]]
        if key in self.replace:
            rows = self.replace[key](rows)
        return [(table[0], rows)]

    def answer(self, conn, sql):
        s = code(sql)
        if s.startswith("USE "):
            db = s[4:].rstrip(";")
            if self.missing_db and db != "master":
                raise RuntimeError(f"Cannot open database \"{db}\" requested by the login.")
            conn.db = db
            return []
        if s == "SELECT @@SPID;":
            return [(["spid"], [(conn.spid,)])]
        if s.startswith("EXEC Tune.usp_TakeWaitSnapshot"):
            self.snapshots.append(s.split("N'")[1].rstrip("';"))
            return []
        if s.startswith("EXEC Tune.usp_WaitDelta"):
            cols = ["WaitType", "WaitingTasksDelta", "WaitTimeMsDelta", "SignalWaitTimeMsDelta"]
            if "before-blocking" in s:
                rows = [("LCK_M_S", 1, self.lock_ms, 0), ("WRITELOG", 3, 40, 5)] if self.lock_ms else [("WRITELOG", 3, 40, 5)]
            else:
                rows = [("LCK_M_S", 1, 4000, 0)] if self.rcsi_ignored else [("WRITELOG", 3, 30, 4)]
            return [(cols, rows)]
        if s == self.diag_text:
            cols = ["BlockedSession", "BlockerSession", "WaitType", "WaitMs", "WaitResource", "BlockerOpenTransactions",
                    "BlockedStatement", "BlockerLastStatement"]
            with self.lock:
                if self.waiting is None:
                    return [(cols, [])]
                return [(cols, [(self.waiting, self.locked_by, "LCK_M_S", 1200, "KEY: 5:72057594:(8194443284a0)", 1,
                                 self.reader_text, "BEGIN TRANSACTION; UPDATE Sales.Orders SET Status = 'Cancelled' WHERE OrderId = 1;")])]
        if "UPDATE Sales.Orders SET Status = 'Cancelled'" in s:
            with self.lock:
                self.locked_by = conn.spid
                self.release.clear()
            return []
        if s == self.reader_text:
            with self.lock:
                blocked = self.locked_by is not None and not (self.rcsi and not self.rcsi_ignored) and not self.never_block
                if blocked:
                    self.waiting = conn.spid
            if blocked:
                self.release.wait(10)
                with self.lock:
                    self.waiting = None
            return [(["Status"], [("Shipped",)])]
        if s.startswith("ROLLBACK TRANSACTION"):
            with self.lock:
                self.locked_by = None
            self.release.set()
            return []
        if "SET READ_COMMITTED_SNAPSHOT ON" in s:
            if self.open != 1:
                raise RuntimeError(f"ALTER DATABASE failed: {self.open - 1} other connection(s) still open")
            self.rcsi = True
            return []
        if "SET READ_COMMITTED_SNAPSHOT OFF" in s:
            self.rcsi = False
            return []
        if s in self.batches:
            key = self.batches[s]
            return self.csv_answer(key, "42" if key == "t01-config-review" else "7")
        return []


def run(server, steps=None, setup=True):
    return lab.run_sqlserver(server.connect, steps or lab.STEPS, setup, sleep=FAST)


def test_all_steps_pass_when_sql_server_behaves(capsys):
    server = FakeServer()
    code = run(server)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "3/3 steps behaved as expected on sqlserver" in out
    assert server.snapshots == ["before-blocking", "after-blocking", "before-rcsi", "after-rcsi"]
    assert server.open == 0                                       # every connection was closed


def test_setup_order_and_databases(capsys):
    server = FakeServer()
    run(server)
    first = lambda f: server.log.index(lab.split_batches(lab.sql_text(f))[0])      # noqa: E731
    assert first("00-create-database.sql") < first("01-schema-and-data.sql") < first("10-tune-tools.sql") < first("t01-config-review.sql")
    assert server.log[server.log.index(lab.split_batches(lab.sql_text("00-create-database.sql"))[0]) - 1] == "USE master;"
    assert "USE ContosoBikesPerf;" in server.log


def test_workload_runs_before_the_query_stats_read(capsys):
    server = FakeServer()
    run(server, [s for s in lab.STEPS if s.key == "t02-top-queries"], setup=False)
    batches = lab.split_batches(lab.sql_text("w01-workload"))
    assert server.log.index(batches[0]) < server.log.index(batches[-1]) < server.log.index(lab.split_batches(lab.sql_text("t02-top-queries"))[-1])


def test_rcsi_is_switched_on_only_after_every_database_connection_is_closed(capsys):
    server = FakeServer()
    assert run(server, [lab.STEPS[2]], setup=False) == 0
    i = [n for n, q in enumerate(server.log) if "SET READ_COMMITTED_SNAPSHOT ON" in q]
    assert len(i) == 1 and server.log[i[0] - 1] == "USE master;"


def test_blocking_step_prints_the_incident_and_the_waits(capsys):
    run(FakeServer(), [lab.STEPS[2]], setup=False)
    out = capsys.readouterr().out
    assert "LCK_M_S" in out and "Reader blocked by the open transaction" in out and "Lock waits (LCK_M_*) with RCSI" in out


def test_a_reader_that_is_never_blocked_fails_the_step(capsys):
    code = run(FakeServer(never_block=True), [lab.STEPS[2]], setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "Reader blocked by the open transaction" in out and "0/1 steps" in out


def test_rcsi_that_does_not_help_fails_the_step(capsys):
    code = run(FakeServer(rcsi_ignored=True), [lab.STEPS[2]], setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "RCSI reader waited under 2 seconds" in out and "Lock waits (LCK_M_*) with RCSI" in out


def test_a_lock_wait_shorter_than_the_blocked_time_fails(capsys):
    code = run(FakeServer(lock_ms=0), [lab.STEPS[2]], setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "Top watch-list wait without RCSI" in out


def test_config_review_rejects_a_changed_default(capsys):
    def tweak(rows):
        return [("cost threshold for parallelism", r[1], "50", r[3]) if r[0].startswith("cost threshold") else r for r in rows]
    code = run(FakeServer(replace={"t01-config-review": tweak}), [lab.STEPS[0]], setup=False)
    assert code == 1 and "expected" in capsys.readouterr().out


def test_top_queries_rejects_the_wrong_ranking(capsys):
    swap = lambda rows: [("seek", "50", "1", "3"), ("scan", "3", "2", "2000")]      # noqa: E731
    code = run(FakeServer(replace={"t02-top-queries": swap}), [lab.STEPS[1]], setup=False)
    assert code == 1 and "row 1" in capsys.readouterr().out


def test_an_error_in_a_step_fails_only_that_step(capsys):
    server = FakeServer()
    original = server.answer

    def boom(conn, sql):
        if "sys.configurations" in sql:
            raise RuntimeError("VIEW SERVER PERFORMANCE STATE permission was denied")
        return original(conn, sql)
    server.answer = boom
    code = run(server, setup=False)
    out = capsys.readouterr().out
    assert code == 1 and "permission was denied" in out and "2/3 steps" in out


def install_fake_driver(monkeypatch, server):
    mod = types.SimpleNamespace(connect=lambda conn_str, autocommit=True: server.connect())
    monkeypatch.setitem(sys.modules, "mssql_python", mod)
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake;Database=master")


def test_main_runs_the_demo_through_the_driver(monkeypatch, capsys):
    server = FakeServer()
    install_fake_driver(monkeypatch, server)
    monkeypatch.setattr(lab, "HOLD_SECONDS", 0.01)
    assert lab.main(["--engine", "sqlserver", "--step", "t01-config-review"]) == 0
    assert "1/1 steps" in capsys.readouterr().out


def test_reset_only_runs_the_cleanup_in_the_lab_database(monkeypatch, capsys):
    server = FakeServer()
    install_fake_driver(monkeypatch, server)
    assert lab.main(["--engine", "sqlserver", "--reset-only"]) == 0
    assert "USE ContosoBikesPerf;" in server.log
    assert lab.split_batches(lab.sql_text("t05-cleanup"))[0] in server.log
    assert "reset:" in capsys.readouterr().out and server.open == 0


def test_reset_only_without_the_database_is_not_an_error(monkeypatch, capsys):
    install_fake_driver(monkeypatch, FakeServer(missing_db=True))
    assert lab.main(["--engine", "sqlserver", "--reset-only"]) == 0
    assert "nothing to do" in capsys.readouterr().out


def test_cli_requires_connection_string_and_known_steps(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        lab.main(["--engine", "sqlserver"])
    with pytest.raises(SystemExit):
        lab.main(["--step", "nope"])
