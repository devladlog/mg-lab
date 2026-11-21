"""The SQL Server path of etl_lab.py against a fake connection: setup and deploy order, the three runs with their
edited DECLARE lines, result comparison. What SQL Server and SSIS really do is checked by the same code on CON-SQL01."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import etl_lab as lab  # noqa: E402
import labdb  # noqa: E402


class FakeCursor:
    def __init__(self, server):
        self.server, self.description, self._rows, self._done = server, None, [], False

    def execute(self, sql):
        self.server.log.append(sql)
        res = self.server.answer(sql)
        if isinstance(res, Exception):
            raise res
        self.description, self._rows = ([(c,) for c in res[0]], res[1]) if res else (None, [])

    def fetchall(self):
        return self._rows

    def nextset(self):
        return None

    def close(self):
        pass


class FakeServer:
    def __init__(self, tamper=None):
        self.log, self.tamper, self.run = [], tamper, -1
        self.results = labdb.split_batches(lab.sql_text("c03-results"))[-1]

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        if "catalog.start_execution" in sql:
            self.run += 1
            return None
        if sql.strip() == self.results:
            table = labdb.read_csv(lab.EXPECTED_DIR / f"{lab.RUNS[self.run].key}.csv")
            if self.tamper:
                table = self.tamper(self.run, table)
            return table[0], [tuple(r) for r in table[1:]]
        return None


def test_full_run_with_setup_and_deploy(capsys):
    server = FakeServer()
    eng = labdb.SqlServerEngine(connection=server)
    assert lab.run_sqlserver(eng, setup=True, deploy=True) == 0
    log = "\n".join(server.log)
    order = [log.index(x) for x in ("DROP DATABASE ContosoBikesEtl", "CREATE DATABASE ContosoBikesEtl", "CREATE SEQUENCE Sales.OrderNumbers",
                                    "CREATE TABLE Etl.RunLog", "catalog.deploy_project", "catalog.create_environment_reference")]
    assert order == sorted(order)
    assert "3/3 runs behaved as expected on sqlserver" in capsys.readouterr().out


def test_each_run_gets_its_logging_level_and_file():
    server = FakeServer()
    lab.run_sqlserver(labdb.SqlServerEngine(connection=server), setup=False, deploy=False)
    runs = [s for s in server.log if "catalog.create_execution" in s]
    assert len(runs) == 3
    assert "@LoggingLevel smallint = 1;" in runs[0] and "@LoggingLevel smallint = 3;" in runs[1]
    assert lab.FILE1 in runs[0] and lab.FILE1 in runs[1] and lab.FILE2 in runs[2]
    assert all("C:\\MGLab\\ssis\\in\\" in r for r in runs)


def test_a_wrong_result_fails_the_run(capsys):
    def tamper(run, table):
        table = [list(r) for r in table]
        if run == 1:
            table[4][1] = "5"          # "Lines inserted" 5 instead of 0: the same file was loaded twice
        return table
    server = FakeServer(tamper)
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), setup=False, deploy=False) == 1
    out = capsys.readouterr().out
    assert "row 4: expected ['Lines inserted', '0'], got ['Lines inserted', '5']" in out and "2/3 runs" in out
