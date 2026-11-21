"""Mistakes this episode is about, reproduced on purpose."""
import copy

import pytest

from flowkit import run_flow
from flowkit.expr import Context, ExpressionError, evaluate

from conftest import SUMMER_RUN, WINTER_RUN, actions, mocks


def _naive_window(flow):
    """The tempting version: format Lisbon midnight with a 'Z' instead of converting it to UTC."""
    bad = copy.deepcopy(flow)
    fmt = "'yyyy-MM-dd''T''HH:mm:ss''Z'''"
    actions(bad)["Week_start_utc"]["inputs"] = f"@formatDateTime(outputs('Week_start_local'), {fmt})"
    actions(bad)["Week_end_utc"]["inputs"] = f"@formatDateTime(addDays(outputs('Week_start_local'), 7), {fmt})"
    return bad


def references(result):
    return sorted(row["reference"] for row in result.actions["Rows"].outputs["body"])


def test_a_z_suffix_doesnt_make_local_time_utc_in_summer(digest):
    good = run_flow(digest, None, mocks(), now=SUMMER_RUN)
    bad = run_flow(_naive_window(digest), None, mocks(), now=SUMMER_RUN)
    assert bad.actions["Week_start_utc"].outputs == "2026-07-06T00:00:00Z"   # an hour late
    assert "PR-00046" in references(good) and "PR-00046" not in references(bad)  # Monday 00:30 is lost
    assert "PR-00047" not in references(good) and "PR-00047" in references(bad)  # next Monday 00:30 sneaks in
    assert bad.actions["Total"].outputs == 19960.5 != good.actions["Total"].outputs


def test_the_same_mistake_is_invisible_in_winter(digest):
    good = run_flow(digest, None, mocks(), now=WINTER_RUN)
    bad = run_flow(_naive_window(digest), None, mocks(), now=WINTER_RUN)
    assert references(good) == references(bad) == ["PR-00012", "PR-00013"]   # tests written in January pass


def test_c2_without_a_locale_is_dollars():
    # formatNumber: "If unspecified, the value is en-us" -> '$17.35'. Pass a locale or use a custom pattern.
    assert evaluate("formatNumber(17.35, 'C2')", Context()) == "$17.35"
    assert evaluate("concat(formatNumber(17.35, '#,##0.00', 'en-US'), ' EUR')", Context()) == "17.35 EUR"


def test_substring_fails_where_slice_clamps():
    ctx = Context()
    ctx.item_stack.append({"Title": "Laptops"})
    with pytest.raises(ExpressionError):
        evaluate("substring(item()?['Title'], 1, sub(indexOf(item()?['Title'], ']'), 1))", ctx)
    assert evaluate("slice(item()?['Title'], 1, indexOf(item()?['Title'], ']'))", ctx) == "aptop"   # no error, wrong answer: why the flow guards it with if()


def test_xml_needs_element_friendly_property_names():
    ctx = Context()
    with pytest.raises(ExpressionError, match="valid XML element name"):
        evaluate("xml(json('{\"root\": {\"row\": [{\"Cost centre\": \"CC-4100\"}]}}'))", ctx)
