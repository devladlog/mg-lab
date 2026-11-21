"""The SQL Server path of security_lab.py against a fake connection: order of setup and before-files, result
comparison, and the safety net that brings an impersonating session back to the runner's user. What SQL Server
really does is checked by the same code during the recording on CON-SQL01."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import security_lab as lab  # noqa: E402


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
    """Knows each step's batches; answers with expected/ unless a test overrides a step. Tracks impersonation:
    a step can be told to 'forget' its REVERT, leaving the session as sales_north."""

    def __init__(self, overrides=None, leave_impersonated=None):
        self.log, self.user, self.overrides = [], "lab_demo", overrides or {}
        self.leave = leave_impersonated
        self.steps = {}
        for s in lab.STEPS:
            for b in labdb.split_batches(lab.sql_text(s.key)):
                self.steps[b] = s.key

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        s = sql.strip()
        if s == "SELECT USER_NAME() AS CurrentUser;":
            return [(["CurrentUser"], [(self.user,)])]
        if s == "REVERT;":
            self.user = "lab_demo"
            return []
        key = self.steps.get(s)
        if key is None:
            return []                                    # setup / before files: DDL, no result sets
        if key == self.leave:
            self.user = "sales_north"
        if key in self.overrides:
            return self.overrides[key](self)
        table = labdb.read_csv(ROOT / "expected" / f"{key}.csv")
        return [(table[0], [tuple(None if v == "NULL" else v for v in r) for r in table[1:]])]


def run(server, capsys, setup=True, steps=None):
    code = lab.run_sqlserver(labdb.SqlServerEngine(connection=server), steps or lab.STEPS, setup=setup)
    return code, capsys.readouterr().out


def test_all_steps_pass_when_sql_server_behaves(capsys):
    code, out = run(FakeSqlServer(), capsys)
    assert code == 0, out
    assert "8/8 steps behaved as expected on sqlserver" in out


def test_setup_order_and_before_files(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    def first_index(fname):
        first = labdb.split_batches(lab.sql_text(fname))[0]
        return server.log.index(first)
    order = [first_index(f) for f in lab.SETUP_FILES]
    assert order == sorted(order)                      # reset first, then episode 5, then this episode
    step_index = {k: server.log.index(labdb.split_batches(lab.sql_text(k))[0]) for k in
                  ("s03-dynamic-sql-breaks-chain", "s04-signed-search", "s05-row-level-security")}
    sign, rls = first_index("14-sign-search-procedure.sql"), first_index("15-row-level-security.sql")
    assert step_index["s03-dynamic-sql-breaks-chain"] < sign < step_index["s04-signed-search"] < rls \
        < step_index["s05-row-level-security"]


def test_session_is_brought_back_after_a_step_that_did_not_revert(capsys):
    server = FakeSqlServer(leave_impersonated="s01-least-privilege")
    code, out = run(server, capsys, setup=False)
    assert code == 0
    assert "REVERT;" in server.log and server.user == "lab_demo"


def test_session_that_cannot_be_reverted_stops_the_run(capsys):
    class Stuck(FakeSqlServer):
        def answer(self, sql):
            if sql.strip() == "REVERT;":
                return []                               # REVERT does nothing: still impersonating
            return super().answer(sql)
    with pytest.raises(RuntimeError, match="not back to lab_demo"):
        run(Stuck(leave_impersonated="s01-least-privilege"), capsys, setup=False)


def test_different_rows_fail_the_step(capsys):
    def leaky(srv):    # RLS not applied: sales_north sees everyone
        table = labdb.read_csv(ROOT / "expected" / "s05-row-level-security.csv")
        rows = [tuple(r) for r in table[1:]]
        rows[0] = ("sales_north", "usp_ListCustomers", "6", "Centre, North, South")
        return [(table[0], rows)]
    code, out = run(FakeSqlServer({"s05-row-level-security": leaky}), capsys)
    assert code == 1 and "row 1: expected" in out and "7/8 steps" in out


def test_an_uncaught_error_fails_the_step(capsys):
    def boom(srv):
        raise RuntimeError("Cannot execute as the database principal because the principal \"sales_north\" "
                           "does not exist (15517)")
    code, out = run(FakeSqlServer({"s01-least-privilege": boom}), capsys)
    assert code == 1 and "unexpected error" in out


def test_reset_only(monkeypatch, capsys):
    server = FakeSqlServer()
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake")
    monkeypatch.setattr(lab, "SqlServerEngine", lambda conn_str: labdb.SqlServerEngine(connection=server))
    assert lab.main(["--engine", "sqlserver", "--reset-only"]) == 0
    reset = labdb.split_batches(lab.sql_text(lab.RESET_FILE))
    assert server.log == reset
    assert "reset:" in capsys.readouterr().out


def test_cli_requires_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        lab.main(["--engine", "sqlserver"])


def test_unknown_check_is_rejected():
    with pytest.raises(ValueError):
        lab.evaluate("plan: inlined", labdb.ScriptResult())
