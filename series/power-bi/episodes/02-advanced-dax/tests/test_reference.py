"""Tests for the Python reference of the episode's DAX measures (src/reference/dax_reference.py)
and for the reproducibility of the star CSVs it reads."""
import csv
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC / "reference"))
sys.path.insert(0, str(SRC / "data"))

import build_star  # noqa: E402
import dax_reference as dax  # noqa: E402
import generate_export  # noqa: E402


@pytest.fixture(scope="module")
def m():
    return dax.Model()


def month(m, y, mo):
    return dax.Ctx().with_dates({d for d in m.dates if d.year == y and d.month == mo})


def year(m, y):
    return dax.Ctx().with_dates({d for d in m.dates if d.year == y})


# --- data -------------------------------------------------------------------------------------

def test_star_csvs_rebuild_byte_identical_from_the_generator(tmp_path):
    export = tmp_path / "export.csv"
    sys.argv = ["generate_export.py", "--out", str(export)]
    generate_export.main()
    build_star.write(build_star.build(build_star.read_export(export)), tmp_path / "star")
    for f in (SRC / "data" / "star").glob("*.csv"):
        assert (tmp_path / "star" / f.name).read_bytes() == f.read_bytes(), f.name


def test_committed_expected_results_are_up_to_date(tmp_path):
    dax.write_expected(dax.run_all(), tmp_path)
    for f in (SRC / "reference" / "expected").glob("*.csv"):
        assert (tmp_path / f.name).read_text() == f.read_text(), f.name


# --- DAX semantics the reference follows ------------------------------------------------------

def test_divide_returns_blank_for_zero_or_blank_denominator():
    assert dax.divide(Decimal(5), Decimal(2)) == Decimal("2.5")
    assert dax.divide(Decimal(5), Decimal(0)) is dax.BLANK
    assert dax.divide(Decimal(5), dax.BLANK) is dax.BLANK


def test_blank_minus_a_number_behaves_like_zero_minus_it():
    assert dax.minus(dax.BLANK, dax.BLANK) is dax.BLANK
    assert dax.minus(dax.BLANK, Decimal(10)) == Decimal(-10)
    assert dax.minus(Decimal(10), dax.BLANK) == Decimal(10)


def test_sameperiodlastyear_february_extends_to_the_29th_in_a_leap_year(m):
    feb_2025 = {d for d in m.dates if d.year == 2025 and d.month == 2}
    py = dax.same_period_last_year(m, feb_2025)
    assert date(2024, 2, 29) in py and len(py) == 29


def test_sameperiodlastyear_single_day_has_no_extension(m):
    assert dax.same_period_last_year(m, {date(2025, 2, 27)}) == {date(2024, 2, 27)}


def test_sameperiodlastyear_before_the_date_table_is_empty(m):
    assert dax.same_period_last_year(m, {date(2024, 6, 1)}) == set()


def test_last_3_months_are_whole_calendar_months(m):
    june = month(m, 2025, 6)
    first = dax.eomonth(max(june.dates), -3) + timedelta(days=1)
    assert first == date(2025, 4, 1)                       # not 31 March
    expected = sum(dax.sales_amount(m, month(m, 2025, mo)) for mo in (4, 5, 6))
    assert dax.sales_last_3_months(m, june) == expected


def test_ytd_restarts_in_january_and_ends_at_the_year_total(m):
    assert dax.sales_ytd(m, month(m, 2025, 1)) == dax.sales_amount(m, month(m, 2025, 1))
    assert dax.sales_ytd(m, month(m, 2025, 12)) == dax.sales_amount(m, year(m, 2025))


def test_prior_year_is_blank_for_the_first_year(m):
    assert dax.sales_py(m, year(m, 2024)) is dax.BLANK
    assert dax.sales_yoy(m, year(m, 2024)) is dax.BLANK


def test_naive_yoy_shows_minus_100_percent_for_the_future_year(m):
    y2026 = year(m, 2026)
    assert dax.sales_amount(m, y2026) is dax.BLANK            # no orders, only January ship dates
    assert dax.sales_py(m, y2026) == dax.sales_amount(m, year(m, 2025))
    assert dax.sales_yoy_naive(m, y2026) == Decimal(-1)
    assert dax.sales_yoy(m, y2026) is dax.BLANK


def test_context_transition_counts_per_customer(m):
    y = year(m, 2025)
    right = dax.customers_over_1k(m, y)
    wrong = dax.customers_over_1k_no_transition(m, y)
    known = sum(1 for c in m.customers if c != dax.UNKNOWN_CUSTOMER)
    assert wrong == known == 300                                # every known customer, sales or not
    manual = sum(1 for c in m.customers if c != -1
                 and (dax.sales_amount(m, dax.Ctx(dates=y.dates, customer=c)) or 0) > 1000)
    assert right == manual < wrong


def test_ranks_run_1_to_n_inside_each_category_and_shares_add_up(m):
    header, rows = dax.q_ranking(m)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["Category"], []).append(r)
    for cat, items in by_cat.items():
        assert [r["Rank"] for r in items] == list(range(1, len(items) + 1)), cat
        assert abs(sum(r["% of Category"] for r in items) - 1) < Decimal("1e-20"), cat


def test_rankx_ties_skip_the_next_rank(tmp_path):
    """Two products with the same sales share rank 1; the next one is rank 3 (ties = Skip)."""
    star = tmp_path / "star"
    star.mkdir()
    (star / "dim_product.csv").write_text(
        "ProductKey,ProductCode,Product,Subcategory,Category,Color\n"
        "1,P1,Alpha,S,C,Red\n2,P2,Beta,S,C,Red\n3,P3,Gamma,S,C,Red\n")
    (star / "dim_customer.csv").write_text("CustomerKey,CustomerCode,Customer,City,Country\n1,C1,A,X,Y\n")
    (star / "dim_date.csv").write_text("Date\n2025-01-01\n")
    (star / "fact_sales.csv").write_text(
        "OrderNumber,LineNumber,OrderDate,ShipDate,CustomerKey,ProductKey,StoreKey,Quantity,UnitPrice,UnitCost\n"
        "SO1,1,2025-01-01,2025-01-01,1,1,1,1,100.00,1\n"
        "SO1,2,2025-01-01,2025-01-01,1,2,1,1,100.00,1\n"
        "SO1,3,2025-01-01,2025-01-01,1,3,1,1,50.00,1\n")
    tiny = dax.Model(star)
    ranks = {p: dax.product_rank(tiny, dax.Ctx().with_product(Category="C", Product=p)) for p in ("Alpha", "Beta", "Gamma")}
    assert ranks == {"Alpha": 1, "Beta": 1, "Gamma": 3}


def test_ship_date_moves_sales_between_years_but_keeps_the_total(m):
    by_order = sum(dax.sales_amount(m, year(m, y)) or 0 for y in (2024, 2025, 2026))
    by_ship = sum(dax.sales_by_ship_date(m, year(m, y)) or 0 for y in (2024, 2025, 2026))
    assert by_order == by_ship
    assert dax.sales_by_ship_date(m, year(m, 2026)) > 0


def test_summarizecolumns_drops_rows_where_every_measure_is_blank(m):
    header, rows = dax.q_context_transition(m)
    assert [r["Year"] for r in rows] == [2024, 2025]           # 2026: both measures BLANK
    header, rows = dax.q_yoy_gotcha(m)
    assert [r["Year"] for r in rows] == [2024, 2025, 2026]     # 2026 kept: Sales PY isn't BLANK


def test_expected_totals_match_episode_1(m):
    assert dax.sales_amount(m, year(m, 2024)) == Decimal("894929.10")
    assert dax.sales_amount(m, year(m, 2025)) == Decimal("967472.88")
