"""The demo SQL files: they parse as T-SQL, the seed loads, the reference queries return what expected/ says and what
an independent Python calculation says. DuckDB stands in for SQL Server here (no Docker on the build machine), so this
proves the data and the queries, not SQL Server behaviour."""

import csv
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
import sqlglot

import reference_db as ref

ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = sorted((ROOT / "src" / "sql").glob("*.sql"))


@pytest.fixture(scope="module")
def con():
    return ref.load_seed()


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_every_sql_file_parses_as_tsql(path):
    text = re.sub(r"\$\(\w+\)", "placeholder", path.read_text(encoding="utf-8"))
    # sqlglot has no EXECUTE AS USER = ... statement; swap it for a harmless one so the rest of the file is still parsed
    text = re.sub(r"EXECUTE AS USER = N'\w+';", "SELECT 1;", text)
    batches = ref.split_go(text)
    assert batches
    for b in batches:
        parsed = sqlglot.parse(b, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)
        assert any(p is not None for p in parsed), b[:60]


def test_no_literal_password_in_any_script():
    for path in (ROOT / "src").rglob("*.sql"):
        for m in re.finditer(r"PASSWORD\s*=\s*N?'([^']*)'", path.read_text(encoding="utf-8"), flags=re.I):
            assert m.group(1).startswith("$("), f"{path.name}: literal password"
    assert "$(AnalystPassword)" in (ROOT / "src" / "sql" / "00-create-database.sql").read_text()


def parse_inserts():
    text = (ROOT / "src" / "sql" / "01-contoso-copilot.sql").read_text(encoding="utf-8")
    tables = {}
    for m in re.finditer(r"INSERT INTO (\w+\.\w+) \(([^)]*)\) VALUES\n(.*?);", text, flags=re.S):
        rows = []
        for r in re.finditer(r"^\s*\((.*)\)[,;]?", m.group(2 + 1), flags=re.M):
            rows.append([x.strip().strip("N").strip("'") for x in re.findall(r"N?'[^']*'|[\d.]+", r.group(1))])
        tables[m.group(1)] = rows
    return tables


def test_seed_row_counts_and_independent_totals(con):
    t = parse_inserts()
    assert {k: len(v) for k, v in t.items()} == {"Sales.Customers": 10, "Sales.Products": 8, "Sales.Orders": 30,
                                                  "Sales.OrderLines": 58}
    for table, n in (("Sales.Customers", 10), ("Sales.Products", 8), ("Sales.Orders", 30), ("Sales.OrderLines", 58)):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == n


def test_q01_matches_independent_python_calculation(con):
    t = parse_inserts()
    orders = {int(r[0]): (int(r[1]), r[2], r[3]) for r in t["Sales.Orders"]}
    names = {int(r[0]): r[1] for r in t["Sales.Customers"]}
    rev = defaultdict(Decimal)
    for r in t["Sales.OrderLines"]:
        cust, day, status = orders[int(r[1])]
        if status != "Cancelled" and "2026-09-01" <= day < "2026-10-01":
            rev[cust] += int(r[3]) * Decimal(r[4])
    top = sorted(rev.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    cols, rows = ref.run_query(con, ROOT / "src" / "queries" / "q01-top-customers.sql")
    assert [(r[0], r[1], r[2]) for r in rows] == [(c, names[c], v) for c, v in top]


def test_q02_matches_independent_python_calculation(con):
    t = parse_inserts()
    orders = {int(r[0]): (r[2], r[3]) for r in t["Sales.Orders"]}
    cat = {int(r[0]): r[2] for r in t["Sales.Products"]}
    rev = defaultdict(Decimal)
    for r in t["Sales.OrderLines"]:
        day, status = orders[int(r[1])]
        if status != "Cancelled":
            rev[(day[:7] + "-01", cat[int(r[2])])] += int(r[3]) * Decimal(r[4])
    cols, rows = ref.run_query(con, ROOT / "src" / "queries" / "q02-monthly-revenue-by-category.sql")
    assert [(str(r[0]), r[1], r[2]) for r in rows] == [(m, c, v) for (m, c), v in sorted(rev.items())]


def test_cancelled_orders_exist_and_are_excluded(con):
    cancelled = con.execute("SELECT COUNT(*) FROM Sales.Orders WHERE Status = 'Cancelled'").fetchone()[0]
    assert cancelled > 0
    total_all = con.execute("SELECT SUM(Quantity * UnitPrice) FROM Sales.OrderLines").fetchone()[0]
    total_view = con.execute("SELECT SUM(Revenue) FROM Reporting.MonthlyRevenue").fetchone()[0]
    assert total_view < total_all


@pytest.mark.parametrize("q", ref.QUERIES, ids=lambda p: p.name)
def test_reference_queries_match_expected_csv(con, q):
    cols, rows = ref.run_query(con, q)
    with (ROOT / "expected" / (q.stem + ".csv")).open(newline="", encoding="utf-8") as fh:
        exp_rows = list(csv.reader(fh))
    assert [c.lower() for c in exp_rows[0]] == [c.lower() for c in cols]
    assert exp_rows[1:] == [[ref.fmt(v) for v in r] for r in rows]


def test_q03_finds_the_customer_without_orders(con):
    cols, rows = ref.run_query(con, ROOT / "src" / "queries" / "q03-customers-without-orders.sql")
    assert rows == [(6, "Eva Newcustomer")]
