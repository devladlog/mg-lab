"""Tests for the T-SQL Advanced Queries episode.

Every query runs locally on DuckDB (transpiled from T-SQL by sqlglot) and its result is compared with
an independent Python computation over the same base rows, so a wrong query can't "pass" just because
expected/ was regenerated from it.
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import tsql_runner as tr  # noqa: E402

SQL = ROOT / "src" / "sql"


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def db():
    engine = tr.DuckDBEngine()
    tr.run_script(engine, SQL / tr.SETUP_FILE)
    yield engine
    engine.close()


def q(db, name: str):
    """Run a query file, return a list of dicts."""
    cols, rows = tr.run_query(db, SQL / name)
    return [dict(zip(cols, r)) for r in rows]


def sql(db, text: str):
    cur = db.execute(text)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def base(db):
    customers = {r["CustomerId"]: r for r in sql(db, "SELECT * FROM Sales.Customers")}
    orders = sql(db, "SELECT * FROM Sales.Orders ORDER BY OrderId")
    employees = {r["EmployeeId"]: r for r in sql(db, "SELECT * FROM HR.Employees")}
    logins = sql(db, "SELECT * FROM App.Logins ORDER BY LoginId")
    return customers, orders, employees, logins


# ---------------------------------------------------------------- the data
def test_seed_row_counts(base):
    customers, orders, employees, logins = base
    assert (len(customers), len(orders), len(employees), len(logins)) == (6, 21, 9, 14)


def test_every_sql_file_parses_with_the_tsql_dialect():
    import sqlglot

    files = sorted(SQL.glob("*.sql"))
    assert len(files) == 12
    for f in files:
        for batch in tr.split_batches(f.read_text(encoding="utf-8")):
            sqlglot.parse(batch, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)


# ---------------------------------------------------------------- expected/ (what the SQL Server run is checked against)
@pytest.mark.parametrize("path", tr.query_files(), ids=lambda p: p.stem)
def test_result_matches_expected_csv(db, path):
    table = tr.to_table(*tr.run_query(db, path))
    assert tr.diff(tr.read_csv(ROOT / "expected" / f"{path.stem}.csv"), table) == []


def test_runner_cli_reports_all_queries_matching(capsys):
    assert tr.main([]) == 0
    assert "10/10 queries match expected/ on duckdb" in capsys.readouterr().out


# ---------------------------------------------------------------- q01 window functions
def test_q01_running_total_and_change(db, base):
    customers, orders, _, _ = base
    monthly = defaultdict(Decimal)
    for o in orders:
        monthly[(customers[o["CustomerId"]]["Region"], o["OrderDate"].replace(day=1))] += o["TotalAmount"]
    expected, running, prev = [], {}, {}
    for (region, month) in sorted(monthly):
        rev = monthly[(region, month)]
        running[region] = running.get(region, Decimal(0)) + rev
        change = None if region not in prev else rev - prev[region]
        prev[region] = rev
        expected.append((region, month, rev, running[region], change))

    rows = q(db, "q01-monthly-running-total.sql")
    got = [(r["Region"], r["MonthStart"], r["Revenue"], r["RunningRevenue"], r["ChangeVsPrev"]) for r in rows]
    assert [tuple(tr.normalize(v) for v in g) for g in got] == [tuple(tr.normalize(v) for v in e) for e in expected]
    # LAG compares with the previous ROW: Centre has no April, so May is compared with March.
    centre_may = next(r for r in rows if r["Region"] == "Centre" and r["MonthStart"].month == 5)
    assert centre_may["ChangeVsPrev"] == Decimal("4170.00") - Decimal("1605.25")


# ---------------------------------------------------------------- q02 top-N per group
def test_q02_row_number_and_cross_apply_agree(db, base):
    customers, orders, _, _ = base
    by_customer = defaultdict(list)
    for o in orders:
        by_customer[o["CustomerId"]].append(o)
    expected = []
    for cid, os_ in by_customer.items():
        for o in sorted(os_, key=lambda o: (-o["TotalAmount"], o["OrderId"]))[:2]:
            expected.append((customers[cid]["CustomerName"], o["OrderId"], o["TotalAmount"]))
    expected.sort(key=lambda t: (t[0], -t[2], t[1]))

    a = [tuple(r.values()) for r in q(db, "q02a-top2-row-number.sql")]
    b = [tuple(r.values()) for r in q(db, "q02b-top2-cross-apply.sql")]
    assert a == b == expected


def test_q02_tie_breaker_picks_the_older_order(db):
    alex = [r["OrderId"] for r in q(db, "q02a-top2-row-number.sql") if r["CustomerName"] == "Alex Demo"]
    assert alex == [10, 1]   # orders 1 and 14 are both 1,250.00; OrderId decides


# ---------------------------------------------------------------- q03 OUTER APPLY
def test_q03_outer_apply_keeps_customers_without_orders(db, base):
    customers, orders, _, _ = base
    rows = {r["CustomerName"]: r for r in q(db, "q03-latest-order-outer-apply.sql")}
    assert len(rows) == len(customers) == 6
    assert rows["Eva Newcustomer"]["OrderId"] is None
    for cid, c in customers.items():
        mine = [o for o in orders if o["CustomerId"] == cid]
        if mine:
            latest = max(mine, key=lambda o: (o["OrderDate"], o["OrderId"]))
            assert rows[c["CustomerName"]]["OrderId"] == latest["OrderId"]


def test_q03_cross_apply_would_drop_them(db):
    text = (SQL / "q03-latest-order-outer-apply.sql").read_text().replace("OUTER APPLY", "CROSS APPLY")
    rows = [tuple(r) for r in db.execute(tr.split_batches(text)[0]).fetchall()]
    assert len(rows) == 5 and all(r[0] != "Eva Newcustomer" for r in rows)


# ---------------------------------------------------------------- q04 gaps and islands
def islands(dates: list[dt.date]) -> list[tuple[dt.date, dt.date, int]]:
    out = []
    for d in sorted(set(dates)):
        if out and (d - out[-1][1]).days == 1:
            out[-1] = (out[-1][0], d, out[-1][2] + 1)
        else:
            out.append((d, d, 1))
    return out


def test_q04_streaks_match_a_python_scan(db, base):
    _, _, _, logins = base
    per_user = defaultdict(list)
    for r in logins:
        per_user[r["UserName"]].append(r["LoginAt"].date())
    expected = [(u, *i) for u in sorted(per_user) for i in islands(per_user[u])]
    got = [(r["UserName"], r["StreakStart"], r["StreakEnd"], r["Days"]) for r in q(db, "q04-login-streaks.sql")]
    assert got == expected
    assert max(e[3] for e in expected) == 4   # rita.sample, 2 to 5 March


def test_q04_islands_need_distinct_days(db):
    text = (SQL / "q04-login-streaks.sql").read_text().replace("SELECT DISTINCT UserName", "SELECT UserName")
    rows = db.execute(tr.split_batches(text)[0]).fetchall()
    alex = [(str(r[1]), str(r[2]), r[3]) for r in rows if r[0] == "alex.demo"]
    # two logins on 1 March shift every later row number by one: the second 1 March row lands in the
    # same group as 5 and 6 March, and a "streak" from 1 to 6 March appears (4 March was never logged).
    assert sorted(alex) == [("2025-03-01", "2025-03-03", 3), ("2025-03-01", "2025-03-06", 3),
                            ("2025-03-09", "2025-03-09", 1)]


# ---------------------------------------------------------------- q05 recursive CTE
def test_q05_levels_and_paths(db, base):
    _, _, employees, _ = base

    def path(eid):
        e = employees[eid]
        return e["FullName"] if e["ManagerId"] is None else f"{path(e['ManagerId'])} > {e['FullName']}"

    rows = q(db, "q05-org-chart-recursive.sql")
    assert len(rows) == len(employees)
    for r in rows:
        assert r["Path"] == path(r["EmployeeId"])
        assert r["Lvl"] == r["Path"].count(" > ")
    assert [r["Path"] for r in rows] == sorted(r["Path"] for r in rows)
    assert max(r["Lvl"] for r in rows) == 3


# ---------------------------------------------------------------- q06 PIVOT
def test_q06_pivot_equals_conditional_aggregation_equals_python(db, base):
    customers, orders, _, _ = base
    cells = defaultdict(Decimal)
    for o in orders:
        cells[(customers[o["CustomerId"]]["Region"], o["OrderDate"].month)] += o["TotalAmount"]
    regions = sorted({c["Region"] for c in customers.values()})
    expected = [(reg, *[cells.get((reg, m)) for m in range(1, 7)]) for reg in regions]

    a = [tuple(r.values()) for r in q(db, "q06a-pivot.sql")]
    b = [tuple(r.values()) for r in q(db, "q06b-conditional-aggregation.sql")]
    assert a == b == expected
    assert a[0][4] is None   # Centre, April: no orders -> NULL, not 0


# ---------------------------------------------------------------- q07 GROUPING SETS
def test_q07_subtotals_add_up(db, base):
    _, orders, _, _ = base
    rows = q(db, "q07-grouping-sets.sql")
    grand = [r for r in rows if r["Region"] == "All regions"]
    assert len(grand) == 1
    assert grand[0]["Revenue"] == sum(o["TotalAmount"] for o in orders) == Decimal("24371.15")
    assert grand[0]["Orders"] == len(orders)
    for region in ("Centre", "North", "South"):
        detail = [r for r in rows if r["Region"] == region and r["Quarter"] != "All quarters"]
        subtotal = next(r for r in rows if r["Region"] == region and r["Quarter"] == "All quarters")
        assert subtotal["Revenue"] == sum(r["Revenue"] for r in detail)
        assert subtotal["Orders"] == sum(r["Orders"] for r in detail)


# ---------------------------------------------------------------- q08 the gotcha
def test_q08_default_frame_repeats_on_ties_rows_frame_does_not(db):
    rows = q(db, "q08-gotcha-default-frame.sql")
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["OrderDate"]].append(r)
    ties = [rs for rs in by_date.values() if len(rs) > 1]
    assert len(ties) == 2   # 15 Jan and 11 Feb
    for rs in ties:
        assert len({r["DefaultFrame"] for r in rs}) == 1          # RANGE: same value for every peer
        assert len({r["RowsFrame"] for r in rs}) == len(rs)       # ROWS: a real running total
    running = Decimal(0)
    for r in rows:
        running += r["TotalAmount"]
        assert r["RowsFrame"] == running
    assert rows[-1]["DefaultFrame"] == rows[-1]["RowsFrame"]


# ---------------------------------------------------------------- the runner itself
def test_split_batches_on_go_lines_only():
    script = "SELECT 1;\nGO\n  go  \nSELECT 'GO' AS x; -- GO\nGOTO_label:\nGO;\n-- only a comment\nGO\n"
    assert tr.split_batches(script) == ["SELECT 1;", "SELECT 'GO' AS x; -- GO\nGOTO_label:"]


def test_transpile_drops_query_hints_and_rewrites_apply():
    out = tr.transpile("SELECT c.a, t.b FROM c CROSS APPLY (SELECT TOP (1) b FROM t WHERE t.a = c.a) AS t "
                       "OPTION (MAXRECURSION 5);")
    assert len(out) == 1
    assert "CROSS JOIN LATERAL" in out[0] and "LIMIT 1" in out[0] and "MAXRECURSION" not in out[0]
    outer = tr.transpile("SELECT * FROM c OUTER APPLY (SELECT TOP (1) b FROM t WHERE t.a = c.a) AS t;")[0]
    assert "LEFT JOIN LATERAL" in outer and "ON TRUE" in outer


def test_transpile_rejects_invalid_tsql():
    with pytest.raises(Exception):
        tr.transpile("SELECT FROM WHERE;")


def test_normalize_makes_drivers_comparable():
    assert tr.normalize(Decimal("480.5")) == tr.normalize(480.5) == "480.50"
    assert tr.normalize(dt.datetime(2025, 1, 1)) == tr.normalize(dt.date(2025, 1, 1)) == "2025-01-01"
    assert tr.normalize(dt.datetime(2025, 3, 1, 9, 0)) == "2025-03-01 09:00:00"
    assert tr.normalize(None) == "NULL" and tr.normalize(7) == "7"


def test_diff_reports_row_and_column_problems():
    exp = [["a", "b"], ["1", "2"]]
    assert tr.diff(exp, [["a", "b"], ["1", "2"]]) == []
    assert tr.diff(exp, [["a", "c"], ["1", "3"]]) == [
        "columns: expected ['a', 'b'], got ['a', 'c']", "row 1: expected ['1', '2'], got ['1', '3']"]


def test_write_expected_reproduces_the_committed_files(tmp_path):
    assert tr.main(["--write-expected", str(tmp_path)]) == 0
    for f in (ROOT / "expected").glob("*.csv"):
        assert (tmp_path / f.name).read_text() == f.read_text(), f.name


def test_sqlserver_engine_needs_a_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        tr.main(["--engine", "sqlserver"])
