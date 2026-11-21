"""The SQL Server path of proc_lab.py, against a fake connection that answers like SQL Server would
(result sets, a showplan with or without a UserDefinedFunction node, an error on the out-of-stock batch).
What SQL Server really does is checked by the same code during the recording on CON-SQL01."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import proc_lab  # noqa: E402

CHECK_ERROR = ('[Microsoft][ODBC Driver][SQL Server]The UPDATE statement conflicted with the CHECK constraint '
               '"CK_Products_StockQty". The conflict occurred in database "ContosoBikesApp", table '
               '"Sales.Products", column \'StockQty\'. (547)')


def showplan(with_udf: bool) -> str:
    udf = ('<ScalarOperator><UserDefinedFunction FunctionName="[ContosoBikesApp].[Sales].[ufn_LineTotal]" />'
           '</ScalarOperator>') if with_udf else ""
    return ('<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan" Version="1.564" '
            'Build="16.0.4325.4"><BatchSequence><Batch><Statements><StmtSimple StatementType="SELECT">'
            f'<QueryPlan><RelOp PhysicalOp="Stream Aggregate" LogicalOp="Aggregate">{udf}</RelOp></QueryPlan>'
            '</StmtSimple></Statements></Batch></BatchSequence></ShowPlanXML>')


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
    """Answers each batch of each step file; `overrides` lets a test make SQL Server misbehave."""

    def __init__(self, overrides=None):
        self.log, self.stats, self.overrides = [], False, overrides or {}
        self.batches = {}
        for step in proc_lab.STEPS:
            for i, b in enumerate(labdb.split_batches(proc_lab.sql_text(step.key))):
                self.batches[b] = (step.key, i)

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        s = sql.strip()
        if s.startswith("SET STATISTICS XML"):
            self.stats = s.endswith("ON;")
            return []
        if s not in self.batches:
            return []                                  # setup batches (DDL, data): no result sets
        key, i = self.batches[s]
        if (key, i) in self.overrides:
            return self.overrides[(key, i)](self)
        if key in ("d03-naive-out-of-stock", "d04-safe-out-of-stock") and i == 0:
            raise RuntimeError(CHECK_ERROR)
        table = labdb.read_csv(ROOT / "expected" / f"{key}.csv")
        sets = [(table[0], [tuple(r) for r in table[1:]])]
        if self.stats:
            sets.append((["Microsoft SQL Server 2005 XML Showplan"],
                         [(showplan(with_udf=key == "r02b-order-totals-no-inlining"),)]))
        return sets


def run(server, capsys, setup=True):
    code = proc_lab.run_sqlserver(labdb.SqlServerEngine(connection=server), proc_lab.STEPS, setup=setup)
    return code, capsys.readouterr().out


def test_all_steps_pass_when_sql_server_behaves(capsys):
    server = FakeSqlServer()
    code, out = run(server, capsys)
    assert code == 0, out
    assert "8/8 steps behaved as expected on sqlserver" in out
    assert out.count("check plan: inlined") == 1 and out.count("check plan: not inlined") == 1
    assert "error raised: [Microsoft]" in out


def test_setup_runs_every_batch_of_the_three_setup_files(capsys):
    server = FakeSqlServer()
    run(server, capsys)
    sent = set(server.log)
    for f in proc_lab.SETUP_FILES:
        for b in labdb.split_batches(proc_lab.sql_text(f)):
            assert b in sent, (f, b[:60])


def test_plans_are_requested_only_for_plan_checks(capsys):
    server = FakeSqlServer()
    run(server, capsys, setup=False)
    on = [i for i, s in enumerate(server.log) if s == "SET STATISTICS XML ON;"]
    assert len(on) == 2                                # r02a and r02b
    assert server.log.count("SET STATISTICS XML OFF;") == 2


def test_inlining_failure_is_reported(capsys):
    def plan_with_udf(srv):
        table = labdb.read_csv(ROOT / "expected" / "r02a-order-totals.csv")
        return [(table[0], [tuple(r) for r in table[1:]]), (["plan"], [(showplan(True),)])]
    code, out = run(FakeSqlServer({("r02a-order-totals", 0): plan_with_udf}), capsys)
    assert code == 1 and "UserDefinedFunction node" in out and "7/8 steps" in out


def test_missing_error_is_a_failure(capsys):
    def no_error(srv):
        return []
    code, out = run(FakeSqlServer({("d04-safe-out-of-stock", 0): no_error}), capsys)
    assert code == 1 and "expected an error mentioning CK_Products_StockQty" in out


def test_wrong_rows_are_a_failure(capsys):
    def half_written(srv):
        return [(["NewOrders", "NewOrderLines", "WheelsetStock", "LockStock", "OpenTransactions"],
                 [(1, 2, 2, 119, 0)])]
    code, out = run(FakeSqlServer({("d04-safe-out-of-stock", 1): half_written}), capsys)
    assert code == 1 and "row 1: expected" in out


def test_a_failed_batch_does_not_stop_the_script():
    res = labdb.SqlServerEngine(connection=FakeSqlServer()).run_script(proc_lab.sql_text("d03-naive-out-of-stock"))
    assert len(res.errors) == 1 and "CK_Products_StockQty" in res.errors[0]
    assert res.columns[0] == "NewOrders"               # batch 2 still ran


def test_setup_error_stops_the_run():
    class Broken(FakeSqlServer):
        def answer(self, sql):
            if "CREATE OR ALTER FUNCTION Sales.ufn_LineTotal" in sql:
                raise RuntimeError("Incorrect syntax")
            return super().answer(sql)
    with pytest.raises(RuntimeError, match="02-functions.sql: Incorrect syntax"):
        proc_lab.run_sqlserver(labdb.SqlServerEngine(connection=Broken()), proc_lab.STEPS, setup=True)


@pytest.mark.parametrize("check,res,ok", [
    ("error: none", labdb.ScriptResult(), True),
    ("error: none", labdb.ScriptResult(errors=["boom"]), False),
    ("error: CK_X", labdb.ScriptResult(errors=["conflicted with CK_X"]), True),
    ("plan: inlined", labdb.ScriptResult(), False),                       # no plan captured
    ("plan: inlined", labdb.ScriptResult(plans=[showplan(False)]), True),
    ("plan: not inlined", labdb.ScriptResult(plans=[showplan(True)]), True),
])
def test_evaluate(check, res, ok):
    assert (proc_lab.evaluate(check, res) is None) == ok


def test_cli_requires_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        proc_lab.main(["--engine", "sqlserver"])


def test_mssql_python_driver_is_importable():
    pytest.importorskip("mssql_python")
