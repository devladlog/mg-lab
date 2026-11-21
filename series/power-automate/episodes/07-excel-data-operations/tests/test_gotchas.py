"""Our four earlier drafts, and the traps they fell into."""
import math

import pytest

from excelfake import scenario, variants
from flowkit import evaluate, Context

from conftest import needs_node

pytestmark = needs_node


def test_without_pagination_only_256_of_400_rows_are_read_and_nothing_says_so(flow):
    o = scenario.run_import(variants.no_pagination(flow))
    assert o.run.status == "Succeeded"
    assert len(o.run.actions["List_price_rows"].outputs["body"]["value"]) == 256
    assert o.result["inserted"] == 0                       # FAB-0381..0395 never arrive
    assert o.run.actions["Rejected_rows"].outputs["body"] == []   # and the bad rows aren't reported either
    assert "0 rejected" in o.mail[0]["emailMessage/Subject"]


def test_without_iso_dates_every_row_is_rejected(flow):
    o = scenario.run_import(variants.serial_dates(flow))
    shaped = o.run.actions["Shape_rows"].outputs["body"]
    assert shaped[0]["validFrom"] == "46357"                # 1 Dec 2026 as an Excel serial number
    assert {r["problem"] for r in shaped if r["sku"].startswith("FAB-00")} == {"Valid from is not a date"}
    assert o.result["updated"] == 0


def test_a_column_name_with_a_dot_comes_back_encoded(flow):
    o = scenario.run_import(variants.unencoded_column(flow))
    first = o.run.actions["List_price_rows"].outputs["body"]["value"][0]
    assert "Item No_x002e_" in first and "Item No." not in first
    assert len(o.run.actions["Rejected_rows"].outputs["body"]) == 400


def test_row_by_row_needs_794_excel_calls_and_misses_the_duplicate(flow):
    o = scenario.run_import(variants.row_by_row(flow))
    assert o.run.status == "Succeeded"
    assert len(o.excel.calls) == 2 + 396 * 2               # Get a row + Update or Add, per valid row
    assert o.excel.minimum_minutes == math.ceil(794 / 100) == 8   # 100 calls per connection per 60 s
    assert o.run.executions > 1000                          # every action in the loop is a Power Platform request
    a, b = [r for r in o.catalogue_rows() if r[0] == "FAB-0007"]
    assert a[2] == scenario.new_price(7) and b[2] == scenario.old_price(7)   # Update a row: first match only
    good = scenario.run_import()
    assert len(good.excel.calls) == 3 and good.run.executions < 20


def test_a_file_bigger_than_the_threshold_fails_loudly(flow):
    o = scenario.run_import(price_wb=scenario.big_price_list(6000))
    assert o.run.status == "Failed" and o.run.terminate_error["code"] == "TooManyRows"
    assert not o.run.ran("Upsert_catalogue")            # Terminate ends the run: nothing is written


@pytest.mark.parametrize("expression,expected", [
    ("isFloat('10,000.00')", True),            # Learn, isFloat example 1 (invariant culture)
    ("float('10,000.333')", 10000.333),        # Learn, float example 1
    ("float('10.000,333', 'de-DE')", 10000.333),  # Learn, float example 2
    ("isFloat('12,50')", True),                # so a Portuguese "12,50" passes isFloat...
    ("float('12,50')", 1250.0),                # ...and becomes 1250: why the flow rejects commas
])
def test_comma_is_a_thousands_separator_in_the_invariant_culture(expression, expected):
    assert evaluate(expression, Context()) == expected


def test_supplier_text_starting_with_a_minus_isnt_written_as_a_formula():
    wb = scenario.price_list()
    wb.tables["Prices"].rows[0][1] = "- 10% promo: stapler"
    o = scenario.run_import(price_wb=wb)
    assert o.result["textsEscaped"] == 1
    assert [r for r in o.catalogue_rows() if r[0] == "FAB-0001"][0][1] == " - 10% promo: stapler"
