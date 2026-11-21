from datetime import date
from pathlib import Path

from vendor_tools.cli import render
from vendor_tools.renewals import load_vendors, total_cost, upcoming_renewals

DATA = Path(__file__).resolve().parents[1] / "data" / "vendors.csv"


def test_load_vendors_reads_four_vendors():
    vendors = load_vendors(DATA)
    assert [v.name for v in vendors][0] == "Fabrikam Cloud"
    assert len(vendors) == 4
    assert total_cost(vendors) == 45000


def test_upcoming_renewals_within_window_sorted_by_date():
    vendors = load_vendors(DATA)
    result = upcoming_renewals(vendors, date(2027, 3, 1), 130)
    assert [v.name for v in result] == ["Fabrikam Cloud", "Northwind Print"]


def test_upcoming_renewals_excludes_past_dates():
    vendors = load_vendors(DATA)
    assert upcoming_renewals(vendors, date(2027, 4, 1), 10) == []


def test_render_lists_total_for_selected_vendors():
    text = render(load_vendors(DATA), date(2027, 3, 1), 130)
    assert "Fabrikam Cloud" in text
    assert text.endswith("Total: 22,600 EUR")
