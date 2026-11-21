import json
import re

import pytest
import sqlglot
from sqlglot import exp

import sql_mirror
from conftest import DAILY, SRC

SQL = SRC / "sql"


def batches(path):
    text = path.read_text(encoding="utf-8")
    return [b.strip() for b in re.split(r"^\s*GO\s*$", text, flags=re.M) if b.strip()]


@pytest.mark.parametrize("name", ["01-create-and-load.sql", "02-late-changes.sql", "03-checks.sql"])
def test_every_batch_parses_as_t_sql(name):
    for b in batches(SQL / name):
        assert sqlglot.parse(b, read="tsql"), b[:60]


def test_the_load_script_creates_the_table_the_model_reads():
    t = (SQL / "01-create-and-load.sql").read_text(encoding="utf-8")
    model = (SRC / "ContosoSalesIR.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
    sql_cols = re.findall(r"^\s{4}(\w+)\s+(?:bigint|char|int|datetime2|varchar|decimal|AS)", t, re.M)
    source_cols = re.findall(r"sourceColumn:\s*(\w+)", model)
    assert set(source_cols) <= set(sql_cols), set(source_cols) - set(sql_cols)
    assert "datetime2(0)" in t and "CREATE CLUSTERED INDEX CIX_Sales_OrderTimestamp" in t
    assert 'Schema = "dbo", Item = "Sales"' in model


def test_the_load_is_deterministic_arithmetic_only():
    t = (SQL / "01-create-and-load.sql").read_text(encoding="utf-8")
    for banned in ("NEWID", "RAND(", "CHECKSUM", "GETDATE", "SYSDATETIME"):
        assert banned not in t
    assert "DECLARE @Rows bigint = 2000000" in t


def test_mirror_matches_the_committed_daily_table_and_totals():
    doc = json.loads(DAILY.read_text(encoding="utf-8"))
    assert doc["rows"] == 2_000_000
    assert sql_mirror.daily(2_000_000) == doc["daily"]
    years = sql_mirror.by_year(doc["daily"])
    assert {y: v[0] for y, v in years.items()} == {2023: 499_655, 2024: 501_020, 2025: 499_660, 2026: 499_665}
    assert sum(v[1] for v in doc["daily"].values()) == 306_000_098_000       # 3,060,000,980.00
    assert sql_mirror.money(306_000_098_000) == "3060000980.00"


def test_mirror_shape():
    r = sql_mirror.row(1)
    assert r["OrderNumber"] == "SO-0000001" and r["LineNumber"] == 1 and r["Quantity"] == 1 + 13 % 5
    assert sql_mirror.row(5)["OrderNumber"] == "SO-0000001" and sql_mirror.row(6)["OrderNumber"] == "SO-0000002"
    d = sql_mirror.daily(1000)
    assert sum(v[0] for v in d.values()) == 1000
    assert all(sql_mirror.row(n)["ModifiedDate"] >= sql_mirror.row(n)["OrderTimestamp"] for n in range(1, 500))
    assert sql_mirror.row(3)["Channel"] in ("Store", "Online")


def test_sql_and_python_use_the_same_constants():
    t = (SQL / "01-create-and-load.sql").read_text(encoding="utf-8")
    for needle in ("(o * 7919) % 1461", "(o * 104729) % 86400", "(o * 31) % 5", "(o * 37) % 600", "(n * 17) % 3", "(n * 13) % 5", "(2000 + (n * 7919) % 98000) / 100.0", "(n - 1) / 5", "'2023-01-01T00:00:00'"):
        assert needle in t, needle
    src = (SRC / "tools" / "sql_mirror.py").read_text(encoding="utf-8")
    for needle in ("(o * 7919) % DAYS", "(o * 104729) % 86400", "(o * 31) % 5", "(o * 37) % 600", "(n * 17) % 3", "(n * 13) % 5", "2000 + (n * 7919) % 98000", "(n - 1) // 5"):
        assert needle in src, needle
    assert "DAYS = 1461" in src and "date(2023, 1, 1)" in src


def test_late_change_script_touches_recent_days_and_one_old_month():
    t = (SQL / "02-late-changes.sql").read_text(encoding="utf-8")
    assert "DATEADD(day, -3, @Today)" in t and "'2023-03-01'" in t and "ModifiedDate = SYSUTCDATETIME()" in t
    tree = sqlglot.parse(batches(SQL / "02-late-changes.sql")[1], read="tsql")
    assert any(isinstance(s, exp.Update) for s in tree)
