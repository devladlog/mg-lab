"""The Python mirror of the M queries rebuilds exactly the star schema of episode 1."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import pq_reference as ref
from build_star import build as build_star
from generate_export import HEADER, generate

SRC = Path(__file__).resolve().parents[1] / "src"
EXPORTS = SRC / "data" / "exports"
TABLES = {"Sales": "fact_sales", "Date": "dim_date", "Product": "dim_product",
          "Customer": "dim_customer", "Store": "dim_store"}


def norm(v):
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    return "" if v is None else str(v)


@pytest.fixture(scope="module")
def star():
    raw = [dict(zip(HEADER, [str(x) for x in r])) for r in generate(42)]
    return build_star(raw)


@pytest.fixture(scope="module")
def pq():
    return ref.build(EXPORTS)


@pytest.mark.parametrize("table", TABLES)
def test_power_query_star_equals_episode_1_star(table, star, pq):
    key = (lambda r: (r["OrderNumber"], int(r["LineNumber"]))) if table == "Sales" else None
    mine = [{k: norm(v) for k, v in r.items()} for r in pq[table]]
    theirs = [{k: norm(v) for k, v in r.items()} for r in star[TABLES[table]]]
    if key:
        mine, theirs = sorted(mine, key=key), sorted(theirs, key=key)
    assert list(mine[0]) == list(theirs[0])            # same columns, same order
    assert mine == theirs


def test_summary_json_is_up_to_date():
    committed = json.loads((SRC / "reference" / "expected" / "summary.json").read_text())
    assert committed == ref.summary(EXPORTS)


def test_expected_totals_match_episode_1(pq):
    assert f"{ref.sales_amount(pq['Sales']):.2f}" == "1862401.98"
    assert sum(r["Quantity"] for r in pq["Sales"]) == 7462
    assert len({r["OrderNumber"] for r in pq["Sales"]}) == 2440


def test_gotcha_wrong_duplicate_or_no_dedupe_changes_the_totals():
    right = ref.sales_amount(ref.sales_export(EXPORTS))
    oldest = ref.sales_amount(ref.sales_export(EXPORTS, keep="oldest"))
    none = ref.sales_amount(ref.sales_export(EXPORTS, dedupe=False))
    assert right < oldest < none
    assert len(ref.sales_export(EXPORTS, dedupe=False)) - len(ref.sales_export(EXPORTS)) == 247


def test_stray_files_are_ignored(tmp_path):
    for p in EXPORTS.glob("sales_2024-0[12].csv"):
        (tmp_path / p.name).write_bytes(p.read_bytes())
    (tmp_path / "notes.txt").write_text("not a csv")
    (tmp_path / "SALES_2024-03.CSV").write_bytes((EXPORTS / "sales_2024-03.csv").read_bytes())  # upper-case extension
    rows = ref.sales_export(tmp_path)
    assert {r["OrderDate"].month for r in rows} == {1, 2, 3}


def test_read_export_rejects_a_decimal_point_and_iso_dates():
    head = ";".join(HEADER) + "\r\n"
    good = "SO1;1;05/01/2024;06/01/2024;C1;N;C;P;S;P;Store;bk-r-100 ;Road;R;B;Red;1;10,50;5,00\r\n"
    rows = ref.fn_read_export((head + good).encode())
    assert rows[0]["UnitPrice"] == Decimal("10.50") and rows[0]["OrderDate"] == date(2024, 1, 5)
    assert rows[0]["ProductCode"] == "BK-R-100"
    with pytest.raises(ValueError):
        ref.fn_read_export((head + good.replace("10,50", "10.50")).encode())
    with pytest.raises(ValueError):
        ref.fn_read_export((head + good.replace("05/01/2024", "2024-01-05")).encode())


def test_date_table_covers_full_years_including_ship_dates(pq):
    days = [r["Date"] for r in pq["Date"]]
    assert days[0] == date(2024, 1, 1) and days[-1] == date(2026, 12, 31)
    assert len(days) == len(set(days)) == (days[-1] - days[0]).days + 1
    assert max(r["ShipDate"] for r in pq["Sales"]).year == 2026


def test_guests_map_to_the_unknown_customer(pq):
    assert pq["Customer"][0]["CustomerKey"] == -1
    keys = {c["CustomerKey"] for c in pq["Customer"]}
    assert all(r["CustomerKey"] in keys for r in pq["Sales"])
    assert any(r["CustomerKey"] == -1 for r in pq["Sales"])
