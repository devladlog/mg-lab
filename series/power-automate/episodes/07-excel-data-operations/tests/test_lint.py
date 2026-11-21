"""Excel lint rules (Learn: Excel Online (Business) connector known issues and throttling)."""
import copy

from excelfake import variants
from flowkit import lint

from conftest import actions


def messages(flow, level=None):
    return [f.message for f in lint(flow) if level is None or f.level == level]


def test_the_solution_flow_is_clean(flow):
    assert lint(flow) == []


def test_list_rows_without_pagination_is_flagged(flow):
    assert any("256 rows by default" in m for m in messages(variants.no_pagination(flow), "warning"))


def test_a_threshold_over_100000_is_an_error(flow):
    bad = copy.deepcopy(flow)
    actions(bad)["List_price_rows"]["runtimeConfiguration"]["paginationPolicy"]["minimumItemCount"] = 250000
    assert any("outside 1-100000" in m for m in messages(bad, "error"))


def test_missing_datetime_format_is_flagged(flow):
    assert any("ISO 8601" in m for m in messages(variants.serial_dates(flow), "warning"))


def test_an_unencoded_column_name_is_an_error(flow):
    assert messages(variants.unencoded_column(flow), "error") == [
        "item()?['Item No.']: Excel column names with . come back encoded; use item()?['Item No_x002e_']"]


def test_row_operations_in_a_loop_are_flagged(flow):
    warns = messages(variants.row_by_row(flow), "warning")
    assert sum("100 calls per connection per 60 seconds" in m for m in warns) == 3


def test_parallel_writes_to_one_workbook_are_an_error(flow):
    bad = variants.row_by_row(flow)
    actions(bad)["Each_price"]["runtimeConfiguration"] = {"concurrency": {"repetitions": 20}}
    assert any("simultaneous modifications" in m for m in messages(bad, "error"))


def test_every_connector_is_solution_aware(flow):
    refs = flow["properties"]["connectionReferences"]
    assert set(refs) == {"shared_sharepointonline", "shared_excelonlinebusiness", "shared_office365"}
    assert all(r["connection"]["connectionReferenceLogicalName"].startswith("cts_") for r in refs.values())
