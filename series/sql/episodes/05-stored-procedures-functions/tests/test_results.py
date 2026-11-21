"""Results: the local DuckDB run against expected/, and every expected/ file against an independent Python
model of the seed data and of what the procedures are documented to do (all-or-nothing vs statement-level)."""
from __future__ import annotations

import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import proc_lab  # noqa: E402

SEED = proc_lab.sql_text("01-schema-and-data.sql")


def rows(table: str) -> list[tuple]:
    """The VALUES tuples of INSERT INTO <table>, parsed with plain regex (no SQL engine involved)."""
    block = re.search(rf"INSERT INTO {re.escape(table)} \(.*?\) VALUES(.*?);", SEED, re.DOTALL).group(1)
    out = []
    for tup in re.findall(r"\(([^()]*)\)", block):
        vals = []
        for v in re.findall(r"N?'[^']*'|[\d.]+", tup):
            vals.append(v.lstrip("N").strip("'") if v.endswith("'") else (Decimal(v) if "." in v else int(v)))
        out.append(tuple(vals))
    return out


CUSTOMERS = {r[0]: r for r in rows("Sales.Customers")}
PRODUCTS = {r[0]: {"name": r[1], "price": r[2], "stock": r[3]} for r in rows("Sales.Products")}
ORDERS = {r[0]: r for r in rows("Sales.Orders")}
LINES = rows("Sales.OrderLines")


def line_total(qty, price, disc) -> Decimal:
    return (qty * price * (100 - disc) / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


def order_totals() -> dict[int, Decimal]:
    totals = {}
    for oid, _, _, qty, price, disc in LINES:
        totals[oid] = totals.get(oid, Decimal(0)) + line_total(qty, price, disc)
    return totals


def expected(key):
    return labdb.read_csv(ROOT / "expected" / f"{key}.csv")


def test_seed_data_shape():
    assert len(CUSTOMERS) == 6 and len(PRODUCTS) == 5 and len(ORDERS) == 8 and len(LINES) == 13
    assert {c[3] for c in CUSTOMERS.values()} == {"North", "Centre", "South"}
    assert 6 not in {o[1] for o in ORDERS.values()}            # Eva Newcustomer has no orders
    assert PRODUCTS[4]["stock"] == 2                           # the wheelset the demo over-orders


def test_order_totals_match_python():
    totals = order_totals()
    want = [["OrderId", "CustomerName", "OrderTotal"]] + [
        [str(oid), CUSTOMERS[ORDERS[oid][1]][1], str(totals[oid])] for oid in sorted(totals)]
    assert expected("r02a-order-totals") == want
    assert expected("r02b-order-totals-no-inlining") == want   # the hint changes the plan, never the rows


def test_customer_order_summary_matches_python():
    totals = order_totals()
    north = sorted((c[1], oid) for oid, o in ORDERS.items() for c in [CUSTOMERS[o[1]]] if c[3] == "North")
    want = [["CustomerName", "OrderId", "OrderDate", "Lines", "OrderTotal"]] + [
        [name, str(oid), ORDERS[oid][2], str(sum(1 for l in LINES if l[0] == oid)), str(totals[oid])]
        for name, oid in north]
    assert expected("r03-customer-orders-apply") == want


def test_local_engine_reproduces_expected(capsys):
    assert proc_lab.run_local(proc_lab.STEPS) == 0
    assert "3/3 local steps match expected/ on duckdb" in capsys.readouterr().out


def test_local_inlining_rewrites_every_call():
    q = proc_lab.local_query("r03-customer-orders-apply")
    assert "ufn_" not in q and "CROSS APPLY (SELECT" in q
    q2 = proc_lab.local_query("r02b-order-totals-no-inlining")
    assert "USE HINT" not in q2 and "ufn_" not in q2


def test_inlining_catalog_expectation():
    # Learn: is_inlineable is 1 for every inline TVF; ufn_DaysSinceOrder calls GETDATE() (time-dependent)
    assert expected("r01-inlining-catalog")[1:] == [
        ["ufn_CustomerOrderSummary", "SQL_INLINE_TABLE_VALUED_FUNCTION", "1"],
        ["ufn_DaysSinceOrder", "SQL_SCALAR_FUNCTION", "0"],
        ["ufn_LineTotal", "SQL_SCALAR_FUNCTION", "1"],
    ]


# ---- a model of the procedure runs, in the order proc_lab runs them (each from the data --setup leaves)
def place_order(stock, lines, atomic: bool):
    """Returns (order_written, lines_written, new_stock). The UPDATE is one statement: if any line would take
    stock below zero the CHECK constraint rejects the whole statement. atomic=True is the safe procedure
    (XACT_ABORT ON + TRY/CATCH + ROLLBACK); atomic=False is the naive one (statement-level rollback, then COMMIT)."""
    fails = any(stock[p] - q < 0 for p, q, _ in lines)
    if not fails:
        new = dict(stock)
        for p, q, _ in lines:
            new[p] -= q
        return True, len(lines), new
    if atomic:
        return False, 0, stock
    return True, len(lines), stock


def test_procedure_steps_match_the_model():
    stock = {p: v["stock"] for p, v in PRODUCTS.items()}
    # d01: Rita Sample, 2 helmets + 1 lock at 10%
    d01 = [(1, 2, Decimal(0)), (3, 1, Decimal(10))]
    ok, n, stock = place_order(stock, d01, atomic=True)
    total = sum(line_total(q, PRODUCTS[p]["price"], d) for p, q, d in d01)
    assert expected("d01-place-order") == [["GotNewOrderId", "Lines", "OrderTotal", "HelmetStock", "LockStock"],
                                           ["yes", str(n), str(total), str(stock[1]), str(stock[3])]]
    # d02: unknown customer 99 -> THROW 50001 before any write
    assert 99 not in CUSTOMERS
    assert expected("d02-unknown-customer")[1] == ["50001", "Unknown customer.", "0"]
    # d03 naive, then d04 safe: 3 wheelsets (2 in stock) + 1 lock
    over = [(4, 3, Decimal(0)), (3, 1, Decimal(0))]
    for key, atomic in (("d03-naive-out-of-stock", False), ("d04-safe-out-of-stock", True)):
        written, n, stock = place_order(stock, over, atomic)
        assert expected(key) == [["NewOrders", "NewOrderLines", "WheelsetStock", "LockStock", "OpenTransactions"],
                                 [str(int(written)), str(n), str(stock[4]), str(stock[3]), "0"]], key


def test_every_step_has_an_expected_file():
    for step in proc_lab.STEPS:
        assert (ROOT / "expected" / f"{step.key}.csv").exists(), step.key
        assert (ROOT / "src" / "sql" / f"{step.key}.sql").exists(), step.key


@pytest.mark.parametrize("name", ["01-schema-and-data.sql", "r02a-order-totals.sql", "r03-customer-orders-apply.sql"])
def test_local_files_transpile(name):
    for batch in labdb.split_batches(proc_lab.sql_text(name)):
        if not labdb.is_sqlserver_only(batch):
            assert labdb.transpile(batch)
