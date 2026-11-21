"""The SQL Server path of ha_lab.py against a fake connection: setup order, the two expected errors, the stopwatch,
the filter and the wildcard compare of the RPO steps, the report. What SQL Server really does is checked by the same
code during the recording on CON-SQL01."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ha_lab as lab  # noqa: E402
import labdb  # noqa: E402

RPO_COLS = ["DatabaseName", "RecoveryModel", "State", "IsStandby", "LastFull", "LastDiff", "LastLog", "MinutesAtRisk"]
T = datetime(2026, 11, 21, 10, 0, 0)
ERRORS = {"h04-standby-write": 'Failed to update database "ContosoBikesHA_Standby" because the database is read-only. (3906)',
          "h06-ship-log-fails": "The log in this backup set begins at LSN 41000000026400001, which is too recent to apply "
                                "to the database. An earlier log backup that includes LSN 41000000025600001 can be restored. (4305)"}


class FakeCursor:
    def __init__(self, server):
        self.server, self.sets, self.description, self._rows = server, [], None, []

    def execute(self, sql):
        self.server.log.append(sql)
        self.sets = self.server.answer(sql)
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


class FakeSqlServer:
    """Answers each step's result query from expected/ (the RPO ones with real-looking rows), and raises the
    documented errors for the batches that must fail."""

    def __init__(self, overrides=None, no_error=()):
        self.log, self.overrides, self.no_error = [], overrides or {}, set(no_error)
        self.result_batch, self.error_batch = {}, {}
        for s in lab.STEPS:
            batches = labdb.split_batches(lab.sql_text(s.sql or s.key))
            self.result_batch.setdefault(batches[-1], []).append(s.key)
            if s.key in ERRORS:
                self.error_batch[next(b for b in batches if b.startswith("DECLARE") or b.startswith("INSERT"))] = s.key
        self.calls = {}

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        s = sql.strip()
        if s in self.error_batch and self.error_batch[s] not in self.no_error:
            raise RuntimeError(ERRORS[self.error_batch[s]])
        keys = self.result_batch.get(s)
        if not keys:
            return []
        n = self.calls[s] = self.calls.get(s, 0) + 1
        key = keys[min(n, len(keys)) - 1]
        if key in self.overrides:
            return self.overrides[key](self)
        if key in ("h01-rpo-before", "h10-rpo-after"):
            rows = {"h01-rpo-before": [("ContosoBikesHA", "FULL", "ONLINE", 0, None, None, None, None),
                                       ("master_like_other", "SIMPLE", "ONLINE", 0, T, None, None, 3)],
                    "h10-rpo-after": [("ContosoBikesHA", "FULL", "RESTORING", 0, T, None, T, 1),
                                      ("ContosoBikesHA_Standby", "FULL", "ONLINE", 0, None, None, None, None),
                                      ("OtherDb", "FULL", "ONLINE", 0, T, None, T, 2)]}[key]
            return [(RPO_COLS, rows)]
        table = labdb.read_csv(ROOT / "expected" / f"{key}.csv")
        return [(table[0], [tuple(r) for r in table[1:]])]


class Clock:
    """A stopwatch that moves 1 s per call; one step can be made slow."""
    def __init__(self, jump=0.0):
        self.t, self.jump, self.calls = 0.0, jump, 0

    def __call__(self):
        self.calls += 1
        self.t += 1.0 if self.calls % 2 else 1.0 + self.jump
        return self.t


def run(server, capsys, setup=True, steps=None, clock=None):
    code = lab.run_sqlserver(labdb.SqlServerEngine(connection=server), steps or lab.STEPS, setup=setup, clock=clock or Clock())
    return code, capsys.readouterr().out


def first(server, f):
    return server.log.index(labdb.split_batches(lab.sql_text(f))[0])


def test_all_steps_pass_when_sql_server_behaves(capsys):
    code, out = run(FakeSqlServer(), capsys)
    assert code == 0, out
    assert "10/10 steps behaved as expected on sqlserver" in out
    assert "check error: contains: database is read-only" in out and "check error: contains: too recent to apply" in out


def test_setup_order_and_data_files(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    assert first(server, "h00-reset.sql") < first(server, "00-create-database.sql") < first(server, "01-schema-and-data.sql")
    order = ["01-schema-and-data.sql", "h01-rpo-exposure.sql", "h02-init-standby.sql", "d01-order-1009.sql", "h03-ship-log.sql",
             "h04-standby-write.sql", "d02-order-1010.sql", "h05-rogue-log-backup.sql", "d03-order-1011.sql",
             "h06-ship-log-fails.sql", "h07-repair-chain.sql", "d04-order-1012.sql", "h08-failover.sql", "h09-write-on-promoted.sql"]
    idx = [first(server, f) for f in order]
    assert idx == sorted(idx)


def test_data_files_run_in_the_primary_and_steps_in_master(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    i = first(server, "d01-order-1009.sql")
    assert server.log[i - 1] == "USE ContosoBikesHA;"
    j = first(server, "h03-ship-log.sql")
    assert "USE master;" in server.log[j - 2:j]


def test_standby_write_must_fail_with_3906(capsys):
    code, out = run(FakeSqlServer(no_error=["h04-standby-write"]), capsys, setup=False, steps=[s for s in lab.STEPS if s.key == "h04-standby-write"])
    assert code == 1 and "expected an error, none was raised" in out


def test_broken_chain_must_fail_with_4305(capsys):
    code, out = run(FakeSqlServer(no_error=["h06-ship-log-fails"]), capsys, setup=False, steps=[s for s in lab.STEPS if s.key == "h06-ship-log-fails"])
    assert code == 1 and "expected an error" in out


def test_a_different_error_is_a_failure(capsys):
    class Other(FakeSqlServer):
        def answer(self, sql):
            if sql.strip() in self.error_batch:
                raise RuntimeError("Cannot open backup device. Operating system error 5(Access is denied.). (3201)")
            return super().answer(sql)
    code, out = run(Other(), capsys, setup=False, steps=[s for s in lab.STEPS if s.key == "h06-ship-log-fails"])
    assert code == 1 and "does not mention" in out


def test_standby_that_moved_after_the_failed_restore_fails_the_step(capsys):
    def moved(srv):
        table = labdb.read_csv(ROOT / "expected" / "h06-ship-log-fails.csv")
        rows = [tuple(r) for r in table[1:]]
        rows[1] = ("Orders on the standby", "11")
        return [(table[0], rows)]
    code, out = run(FakeSqlServer({"h06-ship-log-fails": moved}), capsys)
    assert code == 1 and "row 2: expected" in out and "9/10 steps" in out


def test_failover_over_the_limit_fails(capsys):
    steps = [s for s in lab.STEPS if s.key == "h08-failover"]
    ok_code, ok_out = run(FakeSqlServer(), capsys, setup=False, steps=steps)
    assert ok_code == 0 and "step took" in ok_out
    code, out = run(FakeSqlServer(), capsys, setup=False, steps=steps, clock=Clock(jump=120))
    assert code == 1 and "limit 60 s" in out


def test_rpo_steps_keep_only_the_lab_databases_and_print_verdicts(capsys):
    code, out = run(FakeSqlServer(), capsys)
    assert code == 0
    assert "master_like_other" not in out and "OtherDb" not in out
    assert "RPO verdicts (target 15 min)" in out
    assert "ContosoBikesHA  NO BACKUP" in out
    assert "RESTORING: backups are taken from the database that is ONLINE" in out
    assert "ContosoBikesHA_Standby  SKIPPED" not in out        # the standby is ONLINE and not in standby here: NO BACKUP
    assert "ContosoBikesHA_Standby  NO BACKUP" in out


def test_an_uncaught_error_fails_the_step(capsys):
    def boom(srv):
        raise RuntimeError("Cannot open backup device. Operating system error 5(Access is denied.). (3201)")
    code, out = run(FakeSqlServer({"h02-init-standby": boom}), capsys)
    assert code == 1 and "no result set" in out or "unexpected error" in out


def test_report_exit_code_follows_the_verdicts(monkeypatch, capsys):
    class Report(FakeSqlServer):
        def answer(self, sql):
            if sql.strip() == labdb.split_batches(lab.sql_text("h01-rpo-exposure"))[-1]:
                return [(RPO_COLS, self.rows)]
            return []
    ok = Report(); ok.rows = [("A", "FULL", "ONLINE", 0, T, None, T, 3), ("B", "FULL", "RESTORING", 0, None, None, None, None)]
    assert lab.report(labdb.SqlServerEngine(connection=ok), 15) == 0
    assert "A  OK" in capsys.readouterr().out
    bad = Report(); bad.rows = [("A", "FULL", "ONLINE", 0, T, None, T, 300)]
    assert lab.report(labdb.SqlServerEngine(connection=bad), 15) == 1
    assert "AT RISK" in capsys.readouterr().out


def test_reset_only_runs_h00(monkeypatch, capsys):
    server = FakeSqlServer()
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake")
    monkeypatch.setattr(lab, "SqlServerEngine", lambda conn_str: labdb.SqlServerEngine(connection=server))
    assert lab.main(["--engine", "sqlserver", "--reset-only"]) == 0
    assert server.log == labdb.split_batches(lab.sql_text("h00-reset.sql"))
    assert "reset:" in capsys.readouterr().out


def test_unknown_check_is_rejected():
    with pytest.raises(ValueError):
        lab.evaluate("plan: inlined", labdb.ScriptResult())
