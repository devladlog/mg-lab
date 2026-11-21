"""The T-SQL that can't run locally (functions, procedures), checked with Microsoft's own parser (ScriptDom,
SQL Server 2022 grammar): it parses, and it has the structure the episode claims."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import proc_lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")

SQL_FILES = sorted(p.name for p in (ROOT / "src" / "sql").glob("*.sql"))


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert sum(len(b["statements"]) for b in f["batches"]) > 0


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("CREATE PROCEDURE dbo.p AS BEGIN SELEC 1; END;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


def test_lineno_is_reserved(tmp_path):
    # why the column is LineNumber: LINENO is a T-SQL reserved keyword
    f = tmp_path / "lineno.sql"
    f.write_text("CREATE TABLE dbo.t (OrderId int, LineNo int);\n", encoding="utf-8")
    code, files = tsqlparse.parse(f)
    assert code == 1 and "LineNo" in files[0]["errors"][0]["message"]


def test_safe_procedure_shape():
    p = tsqlparse.modules()["Sales.usp_PlaceOrder"]
    params = {x["name"]: x for x in p["parameters"]}
    assert params["@Lines"]["type"] == "Sales.OrderLineList" and params["@Lines"]["readOnly"]   # TVPs are READONLY
    assert params["@OrderId"]["output"]
    body = p["body"]
    assert {"NoCount=ON", "XactAbort=ON"} <= set(body["setOptions"])
    for node in ("TryCatchStatement", "ThrowStatement", "BeginTransactionStatement",
                 "CommitTransactionStatement", "RollbackTransactionStatement"):
        assert node in body["nodeTypes"], node


def test_naive_procedure_is_the_same_minus_the_safety_net():
    naive = tsqlparse.modules()["Sales.usp_PlaceOrder_Naive"]["body"]
    assert "XactAbort=ON" not in naive["setOptions"]
    assert "TryCatchStatement" not in naive["nodeTypes"] and "ThrowStatement" not in naive["nodeTypes"]
    assert {"BeginTransactionStatement", "CommitTransactionStatement"} <= set(naive["nodeTypes"])
    # same INSERT ... SELECT and UPDATE text as the safe procedure
    text = proc_lab.sql_text("03-procedures.sql")
    safe_part, naive_part = text.split("CREATE OR ALTER PROCEDURE Sales.usp_PlaceOrder_Naive")
    for stmt in ("UPDATE p", "SET p.StockQty = p.StockQty - l.Qty", "JOIN @Lines AS l ON l.ProductId = p.ProductId;",
                 "SELECT @OrderId, ROW_NUMBER() OVER (ORDER BY l.ProductId), l.ProductId, l.Qty, p.ListPrice, l.DiscountPct"):
        assert stmt in safe_part and stmt in naive_part, stmt


def test_user_error_numbers_are_valid_for_throw():
    # Learn: THROW error_number must be >= 50000 and <= 2147483647
    numbers = [int(n) for n in re.findall(r"THROW\s+(\d+)", proc_lab.sql_text("03-procedures.sql"))]
    assert numbers == [50001, 50002, 50003]
    assert all(50000 <= n <= 2_147_483_647 for n in numbers)


def test_function_kinds_and_inlining_preconditions():
    mods = tsqlparse.modules()
    line_total = mods["Sales.ufn_LineTotal"]
    days = mods["Sales.ufn_DaysSinceOrder"]
    summary = mods["Sales.ufn_CustomerOrderSummary"]
    assert line_total["kind"] == days["kind"] == "scalar function"
    assert summary["kind"] == "inline table-valued function"
    # Learn's inlining rules: one RETURN, no time-dependent built-ins, EXECUTE AS CALLER (the default), no INLINE = OFF
    assert len(line_total["returnExpressions"]) == 1
    assert not {"GETDATE", "SYSDATETIME", "CURRENT_TIMESTAMP"} & set(line_total["body"]["functionCalls"])
    assert line_total["options"] == []
    assert "GETDATE" in days["body"]["functionCalls"]          # the reason r01 expects is_inlineable = 0
    assert "SALES.UFN_LINETOTAL" in summary["body"]["functionCalls"]


def test_local_inliner_reads_the_same_bodies_as_scriptdom():
    mods = tsqlparse.modules()
    mine = proc_lab.parse_functions(proc_lab.sql_text("02-functions.sql"))
    assert mine["Sales.ufn_LineTotal"].text == mods["Sales.ufn_LineTotal"]["returnExpressions"][0]
    assert mine["Sales.ufn_LineTotal"].params == [p["name"][1:] for p in mods["Sales.ufn_LineTotal"]["parameters"]]
    sel = mods["Sales.ufn_CustomerOrderSummary"]["selectText"].rstrip(";").strip()
    assert mine["Sales.ufn_CustomerOrderSummary"].text == sel


def test_step_scripts_call_the_right_procedures():
    calls = {}
    for name, f in tsqlparse.parse_all_sql().items():
        calls[name] = {st["text"].split()[1] for b in f["batches"] for st in b["statements"]
                       if st["type"] == "ExecuteStatement"}
    assert calls["d01-place-order.sql"] == {"Sales.usp_PlaceOrder"}
    assert calls["d03-naive-out-of-stock.sql"] == {"Sales.usp_PlaceOrder_Naive"}
    assert calls["d04-safe-out-of-stock.sql"] == {"Sales.usp_PlaceOrder"}
