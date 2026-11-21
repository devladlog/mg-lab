"""The SQL files: generated in sync with the CSVs, parsed as T-SQL, and the same logic run on SQLite (no SQL Server in the container)."""
import re
import sqlite3
import subprocess
import sys
from decimal import Decimal

import pytest
import sqlglot

import expected
import make_sql
from conftest import SRC

SQL = SRC / "sql"


def test_committed_tsql_is_up_to_date():
    files = make_sql.build("tsql")
    assert set(files) <= {p.name for p in SQL.glob("*.sql")}
    for name, text in files.items():
        assert (SQL / name).read_text(encoding="utf-8") == text, name


def test_fact_row_constant_matches_csv():
    assert make_sql.FACT_ROWS == expected.totals()["lines"] == 4071


def batches(text):
    return [b for b in re.split(r"^GO\s*$", text, flags=re.M) if b.strip()]


@pytest.mark.parametrize("path", sorted(SQL.glob("*.sql")), ids=lambda p: p.name)
def test_every_tsql_batch_parses(path):
    n = 0
    for b in batches(path.read_text(encoding="utf-8")):
        stmts = sqlglot.parse(b, read="tsql")
        assert stmts, path.name
        n += len(stmts)
    assert n > 0


def test_insert_batches_respect_the_1000_row_limit():
    text = (SQL / "02-load-data.sql").read_text(encoding="utf-8")
    for stmt in re.split(r"(?=^INSERT INTO)", text, flags=re.M):
        if stmt.startswith("INSERT"):
            rows = len(re.findall(r"^\s*\(", stmt, flags=re.M))
            assert rows <= 1000


def test_view_keeps_the_grain_of_the_aggregation_table():
    view = (SQL / "03-agg-view.sql").read_text(encoding="utf-8")
    assert "GROUP BY f.OrderDate, f.ProductKey, f.StoreKey" in view
    assert "COUNT_BIG(*)" in view


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    out = tmp_path_factory.mktemp("sqlite")
    subprocess.run([sys.executable, str(SRC / "tools" / "make_sql.py"), "--dialect", "sqlite", "--out", str(out)], check=True, capture_output=True)
    con = sqlite3.connect(":memory:")
    for name in ("01-create-database.sql", "02-load-data.sql", "03-agg-view.sql"):
        con.executescript((out / name).read_text(encoding="utf-8"))
    return con, (out / "04-scale-up.sql").read_text(encoding="utf-8")


def agg_numbers(con):
    lines, amount, units = con.execute("SELECT COUNT(*), SUM(Quantity*UnitPrice), SUM(Quantity) FROM FactSales").fetchone()
    rows, a2, u2, l2 = con.execute("SELECT COUNT(*), SUM(LineAmount), SUM(Units), SUM(OrderLines) FROM vwSalesAgg").fetchone()
    return lines, Decimal(str(round(amount, 2))), units, rows, Decimal(str(round(a2, 2))), u2, l2


def test_loaded_data_reconciles_with_the_csv(db):
    db, _ = db
    t = expected.totals()
    lines, amount, units, rows, a2, u2, l2 = agg_numbers(db)
    assert (lines, amount, units) == (t["lines"], t["amount"], t["units"])
    assert (rows, a2, u2, l2) == (t["agg_rows"], t["amount"], t["units"], t["lines"])


def test_aggregation_matches_detail_by_year(db):
    db, _ = db
    for year, amount in expected.by_year().items():
        got = db.execute("SELECT SUM(LineAmount) FROM vwSalesAgg WHERE substr(OrderDate,1,4)=?", (year,)).fetchone()[0]
        assert Decimal(str(round(got, 2))) == amount


def test_scale_up_grows_the_detail_and_not_the_aggregation_grain(db):
    db, scale = db
    t = expected.totals()
    db.executescript(scale)
    lines, amount, units, rows, a2, u2, l2 = agg_numbers(db)
    assert lines == t["lines"] * (make_sql.COPIES + 1) == 2_035_500
    assert amount == t["amount"] * (make_sql.COPIES + 1)
    assert rows == t["agg_rows"]          # same 3,947 groups: that is the point of an aggregation
    assert l2 == lines


def test_budget_file_is_up_to_date_and_covers_every_store_month():
    import make_budget
    assert (SRC / "data" / "budget" / "budget.csv").read_text(encoding="utf-8") == make_budget.render()
    rows = make_budget.build()
    assert len(rows) == 60 and {r[0] for r in rows} == {"Contoso Lisboa", "Contoso Madrid", "Contoso Online", "Contoso Paris", "Contoso Porto"}
