"""Tests for the flat-export -> star schema step (src/data/build_star.py)."""
import csv
import hashlib
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "src" / "data"
sys.path.insert(0, str(DATA))

import build_star  # noqa: E402
import generate_export  # noqa: E402


@pytest.fixture(scope="module")
def export_rows():
    return build_star.read_export(DATA / "raw" / "sales_export.csv")


@pytest.fixture(scope="module")
def star(export_rows):
    return build_star.build(export_rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_generator_is_deterministic_and_matches_committed_csv(tmp_path):
    out = tmp_path / "export.csv"
    sys.argv = ["generate_export.py", "--out", str(out)]
    generate_export.main()
    committed = (DATA / "raw" / "sales_export.csv").read_bytes()
    assert hashlib.sha256(out.read_bytes()).hexdigest() == hashlib.sha256(committed).hexdigest()


def test_committed_star_csvs_are_up_to_date(tmp_path, star):
    build_star.write(star, tmp_path)
    for name in star:
        assert (tmp_path / f"{name}.csv").read_bytes() == (DATA / "star" / f"{name}.csv").read_bytes(), name


def test_fact_grain_is_one_row_per_order_line(export_rows, star):
    fact = star["fact_sales"]
    assert len(fact) == len(export_rows)
    keys = Counter((r["OrderNumber"], r["LineNumber"]) for r in fact)
    assert max(keys.values()) == 1


def test_totals_reconcile_with_the_export(export_rows, star):
    def amount(rows):
        return sum(Decimal(r["UnitPrice"]) * int(r["Quantity"]) for r in rows)
    assert amount(star["fact_sales"]) == amount(export_rows)
    assert sum(r["Quantity"] for r in star["fact_sales"]) == sum(int(r["Quantity"]) for r in export_rows)


def test_fact_has_only_keys_measures_and_the_degenerate_order_number(star):
    assert list(star["fact_sales"][0].keys()) == [
        "OrderNumber", "LineNumber", "OrderDate", "ShipDate",
        "CustomerKey", "ProductKey", "StoreKey", "Quantity", "UnitPrice", "UnitCost"]


@pytest.mark.parametrize("dim,key", [
    ("dim_product", "ProductKey"), ("dim_customer", "CustomerKey"),
    ("dim_store", "StoreKey"), ("dim_date", "Date")])
def test_dimension_keys_are_unique(star, dim, key):
    values = [r[key] for r in star[dim]]
    assert len(values) == len(set(values))


@pytest.mark.parametrize("fk,dim,key", [
    ("ProductKey", "dim_product", "ProductKey"), ("CustomerKey", "dim_customer", "CustomerKey"),
    ("StoreKey", "dim_store", "StoreKey"), ("OrderDate", "dim_date", "Date"), ("ShipDate", "dim_date", "Date")])
def test_every_foreign_key_finds_its_dimension_row(star, fk, dim, key):
    """No referential integrity violations -> Power BI never adds a blank virtual row."""
    keys = {r[key] for r in star[dim]}
    missing = {r[fk] for r in star["fact_sales"]} - keys
    assert not missing


def test_guest_orders_point_to_the_unknown_customer(export_rows, star):
    guests = sum(1 for r in export_rows if not r["CustomerCode"])
    assert guests > 0
    assert sum(1 for r in star["fact_sales"] if r["CustomerKey"] == build_star.UNKNOWN_CUSTOMER_KEY) == guests
    unknown = star["dim_customer"][0]
    assert unknown["CustomerKey"] == -1 and unknown["Customer"] == "Unknown customer"


def test_product_dimension_is_flattened_no_snowflake(star):
    p = star["dim_product"][0]
    assert {"Subcategory", "Category"} <= p.keys()
    # every subcategory belongs to exactly one category -> a clean Category > Subcategory > Product hierarchy
    pairs = {(r["Subcategory"], r["Category"]) for r in star["dim_product"]}
    assert len(pairs) == len({s for s, _ in pairs})


def test_date_table_is_contiguous_unique_and_spans_full_years(star):
    dates = [date.fromisoformat(r["Date"]) for r in star["dim_date"]]
    assert dates[0] == date(dates[0].year, 1, 1)
    assert dates[-1] == date(dates[-1].year, 12, 31)
    assert all(b - a == timedelta(days=1) for a, b in zip(dates, dates[1:]))


def test_date_table_covers_ship_dates_that_spill_into_the_next_year(export_rows, star):
    last_ship = max(date.fromisoformat(r["ShipDate"]) for r in export_rows)
    last_order = max(date.fromisoformat(r["OrderDate"]) for r in export_rows)
    assert last_ship.year == last_order.year + 1          # an order on 31 Dec ships in January
    assert star["dim_date"][-1]["Date"] == f"{last_ship.year}-12-31"


def test_month_sort_columns_are_consistent(star):
    for r in star["dim_date"]:
        assert build_star.MONTHS[r["Month Number"] - 1] == r["Month"]
        assert r["Year Month Number"] == r["Year"] * 100 + r["Month Number"]


def test_surrogate_keys_are_stable_sorted_by_business_key(star):
    codes = [r["ProductCode"] for r in star["dim_product"]]
    assert codes == sorted(codes)
    assert [r["ProductKey"] for r in star["dim_product"]] == list(range(1, len(codes) + 1))
