"""The linter on the digest: clean, and it catches the expression mistakes it was written for."""
import copy

from flowkit import lint

from conftest import actions, sample


def errors(flow):
    return [f.message for f in lint(flow) if f.level == "error"]


def test_the_solution_flow_is_clean(digest):
    assert lint(digest) == []


def test_comparison_samples_are_clean():
    assert lint(sample("total-with-apply-to-each.json")) == []
    assert lint(sample("total-with-xpath.json")) == []


def test_a_typo_in_a_function_name_is_caught(digest):
    bad = copy.deepcopy(digest)
    actions(bad)["Week_start_local"]["inputs"] = "@addDays(startOfDay(convertFromUTC2(utcNow(), 'GMT Standard Time')), -7)"
    assert any("convertFromUTC2() isn't a function" in m for m in errors(bad))


def test_expressions_longer_than_8192_characters_are_an_error(digest):
    bad = copy.deepcopy(digest)
    actions(bad)["Week_start_local"]["inputs"] = "@concat(" + ", ".join(["'abcdefgh'"] * 800) + ")"
    assert any("the limit is 8192" in m for m in errors(bad))


def test_reference_to_a_missing_compose_is_caught(digest):
    bad = copy.deepcopy(digest)
    actions(bad)["Week_start_utc"]["inputs"] = "@convertToUtc(outputs('Week_start'), 'GMT Standard Time')"
    assert any("outputs('Week_start') refers to an action that doesn't exist" in m for m in errors(bad))
