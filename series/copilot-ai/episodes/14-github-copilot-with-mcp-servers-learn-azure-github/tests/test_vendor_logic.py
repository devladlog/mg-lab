from datetime import date

import pytest

from vendor_mcp import data

TODAY = date(2027, 3, 1)


def test_load_has_four_vendors_totalling_45000():
    vendors = data.load()
    assert len(vendors) == 4
    assert sum(v["annual_cost_eur"] for v in vendors) == 45000


def test_notice_deadline_is_renewal_minus_notice_days():
    fabrikam = data.load()[0]
    assert data.notice_deadline(fabrikam) == date(2026, 12, 31)


def test_list_renewals_window_sorted_and_flags_passed_notice():
    rows = data.list_renewals(data.load(), 130, TODAY)
    assert [r["name"] for r in rows] == ["Fabrikam Cloud", "Northwind Print"]
    assert rows[0]["notice_deadline_passed"] is True
    assert rows[1]["notice_deadline_passed"] is False
    assert rows[0]["days_to_renewal"] == 30


def test_list_renewals_excludes_past_renewals_and_rejects_negative_window():
    assert data.list_renewals(data.load(), 10, date(2027, 4, 1)) == []
    with pytest.raises(data.VendorError):
        data.list_renewals(data.load(), -1, TODAY)


def test_find_vendor_partial_name_unknown_and_ambiguous():
    vendors = data.load()
    assert data.find_vendor(vendors, "northwind", TODAY)["owner"] == "Riley Demo"
    with pytest.raises(data.VendorError, match="no vendor matches"):
        data.find_vendor(vendors, "Litware", TODAY)
    with pytest.raises(data.VendorError, match="several vendors"):
        data.find_vendor(vendors, "o", TODAY)  # matches more than one name


def test_parse_today_validates_iso_dates():
    assert data.parse_today("2027-03-01") == date(2027, 3, 1)
    with pytest.raises(data.VendorError):
        data.parse_today("01/03/2027")
