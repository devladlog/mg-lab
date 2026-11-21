"""The expression language, checked against examples from the Learn functions reference."""
import pytest

from flowkit.expr import Context, ExpressionError, evaluate, evaluate_value

from conftest import NOW


@pytest.fixture
def ctx():
    item = {"Title": "VPN down", "Priority": {"Value": "High"}, "Author": None}
    return Context(trigger_outputs={"headers": {}, "body": item}, now=NOW)


def test_null_ignore_operator_returns_null_instead_of_failing(ctx):
    assert evaluate("triggerBody()?['Author']?['Email']", ctx) is None
    with pytest.raises(ExpressionError):
        evaluate("triggerBody()['Author']['Email']", ctx)  # no '?': the run fails


def test_missing_property_needs_question_mark(ctx):
    assert evaluate("triggerBody()?['DueDate']", ctx) is None
    with pytest.raises(ExpressionError):
        evaluate("triggerBody()['DueDate']", ctx)


def test_designer_slash_path_shorthand(ctx):
    assert evaluate("triggerOutputs()?['body/Priority/Value']", ctx) == "High"


@pytest.mark.parametrize("expression, expected", [
    ("addHours('2018-03-15T00:00:00Z', 10)", "2018-03-15T10:00:00.0000000Z"),   # Learn example 1
    ("addHours('2018-03-15T15:00:00Z', -5)", "2018-03-15T10:00:00.0000000Z"),   # Learn example 2
    ("equals(true, 1)", True),                                                 # Learn example
    ("equals('abc', 'abcd')", False),                                          # Learn example
    ("toLower('Hello World')", "hello world"),
    ("less('banana', 'apple')", False),
    ("startsWith('[TEST] printer', '[test]')", True),   # startsWith isn't case-sensitive
    ("contains(createArray('High', 'Normal'), 'high')", False),  # contains is case-sensitive
    ("div(11, 5)", 2),
    ("coalesce(null, '', 'x')", ""),                   # coalesce skips null, not empty strings
    ("formatDateTime('2026-01-05T13:07:00Z', 'yyyy-MM-dd HH:mm')", "2026-01-05 13:07"),
    ("greater(ticks('2026-03-18'), ticks('2026-03-15'))", True),
])
def test_reference_examples(expression, expected):
    assert evaluate(expression, Context(now=NOW)) == expected


def test_utcnow_uses_round_trip_format():
    assert evaluate("utcNow()", Context(now=NOW)) == "2026-01-05T09:00:00.0000000Z"


def test_interpolation_builds_strings(ctx):
    assert evaluate_value("Ticket: @{triggerBody()?['Title']} (@{triggerBody()?['Priority']?['Value']})", ctx) \
        == "Ticket: VPN down (High)"
    assert evaluate_value("@@mention", ctx) == "@mention"


def test_comparing_null_with_a_number_fails_like_the_engine():
    with pytest.raises(ExpressionError, match="greaterOrEquals"):
        evaluate("greaterOrEquals(null, 500)", Context())


def test_if_evaluates_both_branches():
    # The engine evaluates every argument, so a guard inside if() doesn't protect the other branch.
    with pytest.raises(ExpressionError):
        evaluate("if(true, 'ok', createArray()[3])", Context())


def test_parse_errors_are_reported():
    with pytest.raises(ExpressionError, match="Expected"):
        evaluate("equals(triggerBody()?['Title'], 'x'", Context())
