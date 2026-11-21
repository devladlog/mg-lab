from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from contoso_azure.domain import (
    load_approvers,
    pack_document,
    parse_requests,
    priority_for,
    route_for,
)


@pytest.fixture
def parsed(requests_csv: bytes):  # type: ignore[no-untyped-def]
    return parse_requests(requests_csv.decode("utf-8"))


@pytest.mark.parametrize(
    ("budget", "expected"),
    [("49999.99", "Normal"), ("50000", "High"), ("249999.99", "High"), ("250000", "Board")],
)
def test_priority_boundaries_use_greater_or_equal(budget: str, expected: str) -> None:
    assert priority_for(Decimal(budget)) == expected


def test_nine_valid_rows_and_four_rejected_with_row_numbers(parsed) -> None:  # type: ignore[no-untyped-def]
    assert len(parsed.valid) == 9
    assert [(r.row, r.error_id) for r in parsed.rejected] == [
        (9, "invalid_budget"),
        (10, "invalid_budget"),
        (11, "invalid_code"),
        (13, "invalid_date"),
    ]
    assert parsed.rejected[0].message == "PR-2026-0308 budget 'abc' is not a positive number."


def test_money_is_decimal_and_thousands_separators_are_accepted(parsed) -> None:  # type: ignore[no-untyped-def]
    by_code = {r.code: r for r in parsed.valid}
    assert by_code["PR-2026-0302"].budget == Decimal("49999.99")
    assert by_code["PR-2026-0306"].budget == Decimal(75000)
    assert by_code["PR-2026-0306"].submitted == date(2026, 11, 6)
    assert by_code["PR-2026-0303"].priority == "High"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "0", "-1", ""])
def test_budgets_that_are_not_positive_finite_numbers_are_rejected(bad: str) -> None:
    text = f"code,title,department,budget,submitted\nPR-2026-0001,T,IT,{bad},2026-11-01\n"
    result = parse_requests(text)
    assert not result.valid
    assert result.rejected[0].error_id == "invalid_budget"


def test_a_byte_order_mark_breaks_the_first_column_unless_it_is_decoded_as_utf8_sig() -> None:
    raw = "﻿code,title,department,budget,submitted\nPR-2026-0001,T,IT,1000,2026-11-01\n".encode()
    assert not parse_requests(raw.decode("utf-8")).valid  # the first column is now called '﻿code'
    assert len(parse_requests(raw.decode("utf-8-sig")).valid) == 1


def test_routes_by_priority_and_uses_the_spelling_from_the_approvers_file(
    parsed,
    approvers_text: str,  # type: ignore[no-untyped-def]
) -> None:
    directory = load_approvers(approvers_text)
    routes = {r.code: route_for(r, directory) for r in parsed.valid}
    assert [a.role for a in routes["PR-2026-0301"].approvers] == ["Manager"]  # type: ignore[union-attr]
    assert [a.role for a in routes["PR-2026-0303"].approvers] == ["Manager", "Finance"]  # type: ignore[union-attr]
    assert [a.name for a in routes["PR-2026-0304"].approvers] == ["Alex Demo", "Sam Demo", "Taylor Demo"]  # type: ignore[union-attr]
    assert routes["PR-2026-0306"].department == "IT"  # type: ignore[union-attr]  # the CSV said "it"
    assert routes["PR-2026-0311"] is None  # Legal is not in the approvers file


def test_pack_document_keeps_decimals_exact_and_serializes_to_json(
    parsed,
    approvers_text: str,  # type: ignore[no-untyped-def]
) -> None:
    directory = load_approvers(approvers_text)
    route = route_for(next(r for r in parsed.valid if r.code == "PR-2026-0302"), directory)
    assert route is not None
    document = pack_document(route)
    assert json.loads(json.dumps(document))["request"]["budget"] == "49999.99"
    with pytest.raises(TypeError, match="Decimal"):
        json.dumps({"budget": Decimal("49999.99")})  # the gotcha the string avoids
