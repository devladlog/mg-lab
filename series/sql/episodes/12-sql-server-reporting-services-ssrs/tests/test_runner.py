"""The SQL Server path of rpt_lab.py against a fake connection: setup order, the password only in memory, result comparison."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import rpt_lab as lab  # noqa: E402


class FakeCursor:
    def __init__(self, server):
        self.server, self.description, self._rows = server, None, []

    def execute(self, sql):
        self.server.log.append(sql)
        res = self.server.answer(sql)
        self.description, self._rows = ([(c,) for c in res[0]], res[1]) if res else (None, [])

    def fetchall(self):
        return self._rows

    def nextset(self):
        return None

    def close(self):
        pass


class FakeServer:
    def __init__(self, tamper=None):
        self.log, self.tamper = [], tamper
        self.answers = {}
        for step in lab.STEPS:
            batch = [b for b in labdb.split_batches(lab.sql_text(step.key)) if b.lstrip().upper().startswith(("SELECT", "EXECUTE AS"))]
            self.answers[step.key] = labdb.split_batches(lab.sql_text(step.key))

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        for step in lab.STEPS:
            last = self.answers[step.key][-1 if step.key != "r06-permissions-check" else 1]
            if sql.strip() == last.strip():
                table = labdb.read_csv(lab.EXPECTED_DIR / f"{step.key}.csv")
                if self.tamper:
                    table = self.tamper(step.key, [list(r) for r in table])
                return table[0], [tuple(r) for r in table[1:]]
        return None


def test_full_run_with_setup(capsys):
    server = FakeServer()
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), setup=True, password="Not-A-Real-Pw-1!") == 0
    log = "\n".join(server.log)
    order = [log.index(x) for x in ("DROP DATABASE ContosoBikesRpt", "CREATE DATABASE ContosoBikesRpt", "CREATE TABLE Sales.Customers",
                                    "CREATE OR ALTER PROCEDURE Rpt.usp_SalesByProduct", "CREATE LOGIN rs_reader")]
    assert order == sorted(order)
    assert "4/4 steps behaved as expected on sqlserver" in capsys.readouterr().out


def test_password_reaches_the_server_but_is_never_in_the_repo_file():
    server = FakeServer()
    lab.run_sqlserver(labdb.SqlServerEngine(connection=server), setup=True, password="Not-A-Real-Pw-1!")
    assert any("Not-A-Real-Pw-1!" in s for s in server.log)
    assert "Not-A-Real-Pw-1!" not in lab.sql_text("r02-reader-login")


def test_password_with_a_quote_is_escaped():
    assert "N'it''s'" in lab.reader_script("it's")


def test_a_wrong_result_fails_the_step(capsys):
    def tamper(key, table):
        if key == "r03-sales-by-product":
            table[1][3] = "9999.99"
        return table
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=FakeServer(tamper)), setup=False, password=None) == 1
    assert "3/4 steps" in capsys.readouterr().out


def test_a_leaked_permission_fails_the_step(capsys):
    def tamper(key, table):
        if key == "r06-permissions-check":
            table[3][1] = "1"       # rs_reader can read Sales.Orders
        return table
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=FakeServer(tamper)), setup=False, password=None) == 1
    assert "SELECT on Sales.Orders" in capsys.readouterr().out
