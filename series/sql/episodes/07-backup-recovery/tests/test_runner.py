"""The SQL Server path of backup_lab.py against a fake connection: setup order, the expected failure of b01, the
before-files, result comparison, and the restore planner check fed from a fake msdb. What SQL Server really does is
checked by the same code during the recording on CON-SQL01."""
from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import backup_lab as lab  # noqa: E402
import labdb  # noqa: E402

BACKUP = "C:\\SQL\\Backup\\"
MARK = datetime(2026, 11, 21, 10, 2, 45, 120000)


def msdb_rows(skip=None):
    def r(kind, minute, first, last, name, copy_only=0):
        t = datetime(2026, 11, 21, 10, minute, 0)
        return (kind, t, t.replace(second=30), Decimal(first), Decimal(last), Decimal(first), copy_only, BACKUP + name)
    rows = [r("D", 0, 100, 200, "MGLab_ContosoBikesBackup_Full.bak"), r("I", 1, 100, 300, "MGLab_ContosoBikesBackup_Diff.bak"),
            r("L", 2, 200, 400, "MGLab_ContosoBikesBackup_Log1.trn"), r("L", 3, 400, 600, "MGLab_ContosoBikesBackup_Log2.trn")]
    return [x for x in rows if not (skip and skip in x[-1])]


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
    def __init__(self, overrides=None, history_skip=None):
        self.log, self.overrides, self.history_skip = [], overrides or {}, history_skip
        self.result_batch = {}                       # last batch of a step file -> step key
        for s in lab.STEPS:
            if s.result:
                self.result_batch[labdb.split_batches(lab.sql_text(s.key))[-1]] = s.key
        self.history = labdb.split_batches(lab.sql_text("msdb-history.sql"))[0]

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        s = sql.strip()
        if s == self.history:
            cols = ["type", "backup_start_date", "backup_finish_date", "first_lsn", "last_lsn", "checkpoint_lsn",
                    "is_copy_only", "physical_device_name"]
            return [(cols, msdb_rows(self.history_skip))]
        if "FROM ContosoBikesBackup.dbo.RecoveryMarks" in s:
            return [(["MarkTime"], [(MARK,)])]
        if "InstanceDefaultDataPath" in s:
            return [(["d", "l"], [("C:\\SQL\\Data\\", "C:\\SQL\\Log")])]
        if s.startswith("BACKUP LOG ContosoBikesBackup") and "Log0" in s or ("Log0.trn" in s and "BACKUP LOG" in s):
            raise RuntimeError("BACKUP LOG cannot be performed because there is no current database backup. (4214)")
        key = self.result_batch.get(s)
        if key is None:
            return []
        if key in self.overrides:
            return self.overrides[key](self)
        table = labdb.read_csv(ROOT / "expected" / f"{key}.csv")
        return [(table[0], [tuple(r) for r in table[1:]])]


def run(server, capsys, setup=True, steps=None):
    code = lab.run_sqlserver(labdb.SqlServerEngine(connection=server), steps or lab.STEPS, setup=setup)
    return code, capsys.readouterr().out


def test_all_steps_pass_when_sql_server_behaves(capsys):
    code, out = run(FakeSqlServer(), capsys)
    assert code == 0, out
    assert "7/7 steps behaved as expected on sqlserver" in out
    assert "planner picked: MGLab_ContosoBikesBackup_Full.bak -> MGLab_ContosoBikesBackup_Diff.bak" in out


def test_setup_order_and_before_files(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    first = lambda f: server.log.index(labdb.split_batches(lab.sql_text(f))[0])      # noqa: E731
    assert first("b00-reset.sql") < first("00-create-database.sql") < first("01-schema-and-data.sql")
    assert first("01-schema-and-data.sql") < first("b01-log-before-full.sql") < first("b02-full-backup.sql")
    assert first("b02-full-backup.sql") < first("d01-orders-after-full.sql") < first("b03-differential-backup.sql") \
        < first("d02-order-after-diff.sql") < first("b04-log-backup.sql") < first("b05-incident.sql") \
        < first("b06-restore-copy.sql") < first("b07-verify-and-repair.sql")


def test_data_files_run_in_the_live_database(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    i = server.log.index(labdb.split_batches(lab.sql_text("d01-orders-after-full.sql"))[0])
    assert server.log[i - 1] == "USE ContosoBikesBackup;"


def test_b01_must_fail_with_the_documented_message(capsys):
    code, out = run(FakeSqlServer(), capsys, setup=False, steps=lab.STEPS[:1])
    assert code == 0 and "no current database backup" in out


def test_b01_succeeding_is_a_failure(capsys):
    class Lenient(FakeSqlServer):
        def answer(self, sql):
            return [] if "Log0" in sql else super().answer(sql)
    code, out = run(Lenient(), capsys, setup=False, steps=lab.STEPS[:1])
    assert code == 1 and "expected an error, none was raised" in out


def test_b01_wrong_error_is_a_failure(capsys):
    class Other(FakeSqlServer):
        def answer(self, sql):
            if "Log0" in sql:
                raise RuntimeError("Cannot open backup device (3201)")
            return super().answer(sql)
    code, out = run(Other(), capsys, setup=False, steps=lab.STEPS[:1])
    assert code == 1 and "does not mention" in out


def test_restore_that_leaves_the_bad_prices_fails(capsys):
    def stopped_too_late(srv):
        table = labdb.read_csv(ROOT / "expected" / "b06-restore-copy.csv")
        rows = [tuple(r) for r in table[1:]]
        rows[1] = ("Products priced at 0 in the copy", "5")
        return [(table[0], rows)]
    code, out = run(FakeSqlServer({"b06-restore-copy": stopped_too_late}), capsys)
    assert code == 1 and "row 2: expected" in out and "6/7 steps" in out


def test_an_uncaught_error_fails_the_step(capsys):
    def boom(srv):
        raise RuntimeError("Cannot open backup device. Operating system error 5(Access is denied.). (3201)")
    code, out = run(FakeSqlServer({"b02-full-backup": boom}), capsys)
    assert code == 1 and "unexpected error" in out


def test_planner_disagreeing_with_the_sql_fails_the_restore_step(capsys):
    code, out = run(FakeSqlServer(history_skip="Diff"), capsys)
    assert code == 1 and "planner picked" in out and "expected" in out


def test_plan_option_prints_the_restore_statements(monkeypatch, capsys):
    server = FakeSqlServer()
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake")
    monkeypatch.setattr(lab, "SqlServerEngine", lambda conn_str: labdb.SqlServerEngine(connection=server))
    assert lab.main(["--engine", "sqlserver", "--plan"]) == 0
    out = capsys.readouterr().out
    assert out.count("RESTORE") == 5 and "STOPAT = '2026-11-21T10:02:45.120'" in out
    assert "N'C:\\SQL\\Data\\MGLab_ContosoBikesRecovered.mdf'" in out and "N'C:\\SQL\\Log\\MGLab_ContosoBikesRecovered_log.ldf'" in out


def test_reset_only(monkeypatch, capsys):
    server = FakeSqlServer()
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake")
    monkeypatch.setattr(lab, "SqlServerEngine", lambda conn_str: labdb.SqlServerEngine(connection=server))
    assert lab.main(["--engine", "sqlserver", "--reset-only"]) == 0
    assert server.log == labdb.split_batches(lab.sql_text("b00-reset.sql"))
    assert "reset:" in capsys.readouterr().out


def test_cli_requires_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        lab.main(["--engine", "sqlserver"])


def test_unknown_check_is_rejected():
    with pytest.raises(ValueError):
        lab.evaluate("plan: inlined", labdb.ScriptResult())
