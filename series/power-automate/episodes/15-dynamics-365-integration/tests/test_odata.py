"""Filter text: building, checking (rules from Learn) and evaluating."""
import datetime as dt

import pytest

from d365kit import FilterError, bind, check_filter, evaluate_filter, literal, quote
from conftest import sample


def codes(text):
    return [f.code for f in check_filter(text)]


def test_quote_doubles_single_quotes_like_learn():
    assert quote("O'Bryan") == "'O''Bryan'"
    assert evaluate_filter("lastname eq " + quote("O'Bryan"), {"lastname": "o'bryan"})  # case insensitive


def test_literals():
    assert literal(True) == "true" and literal(None) == "null" and literal(5000) == "5000"
    assert literal(dt.date(2026, 11, 21)) == "2026-11-21"
    assert literal(dt.datetime(2026, 11, 21, 9, 0, tzinfo=dt.timezone.utc)) == "2026-11-21T09:00:00Z"
    assert literal("a'b") == "'a''b'"


def test_bind_is_entityset_parenthesis_id():
    g = "00000000-0000-0000-0000-0000000000b1"
    assert bind("opportunities", g) == f"opportunities({g})"
    with pytest.raises(ValueError):
        bind("Opportunity", g)
    with pytest.raises(ValueError):
        bind("opportunities", "not-a-guid")


@pytest.mark.parametrize("text,code", [
    ("$filter=statecode eq 1", "ODATA001"),
    ("name eq 'O'Bryan'", "ODATA002"),
    ("(statecode eq 1", "ODATA003"),
    ("startswith(name,'%abc')", "ODATA004"),
    ("contains(name,'R&D')", "ODATA005"),
])
def test_check_filter_finds_what_learn_warns_about(text, code):
    assert code in codes(text)


def test_a_clean_filter_has_no_findings():
    assert check_filter("statecode eq 0 and estimatedclosedate lt 2026-11-21") == []


def test_more_than_500_conditions_is_an_error():
    big = " or ".join(f"estimatedvalue eq {i}" for i in range(501))
    assert "ODATA006" in codes(big)


def test_evaluator_comparisons_and_logic():
    won = sample("opportunity-won.json")
    assert evaluate_filter("statecode eq 1", won)
    assert not evaluate_filter("statecode eq 0", won)
    assert evaluate_filter("statecode eq 1 and estimatedvalue ge 5000", won)
    assert evaluate_filter("statecode eq 0 or estimatedvalue gt 12000", won)
    assert evaluate_filter("not (statecode eq 0)", won)
    assert evaluate_filter("contains(name,'LAPTOP')", won)  # string filters are case insensitive (Learn)
    assert evaluate_filter("_ownerid_value eq 00000000-0000-0000-0000-0000000000e1", won)
    assert evaluate_filter("estimatedclosedate eq null", won)


def test_evaluator_dates():
    row = {"estimatedclosedate": "2026-11-02"}
    assert evaluate_filter("estimatedclosedate lt 2026-11-21", row)
    assert not evaluate_filter("estimatedclosedate lt 2026-11-02", row)
    assert evaluate_filter("estimatedclosedate le 2026-11-02T00:00:00Z", row)


def test_evaluator_walks_lookup_paths():
    row = {"parentaccountid": {"name": "Fabrikam"}}
    assert evaluate_filter("parentaccountid/name eq 'fabrikam'", row)


@pytest.mark.parametrize("text", ["statecode eq", "statecode == 1", "Microsoft.Dynamics.CRM.Between(a,b)", "a eq 1 )"])
def test_evaluator_refuses_what_it_does_not_understand(text):
    with pytest.raises(FilterError):
        evaluate_filter(text, {"statecode": 1})
