from __future__ import annotations

import sys
import warnings
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

import digest  # noqa: E402
from digest import Accepted, RawRequest, Rejected, Route  # noqa: E402


def raw(code: str = "PR-1", budget: str = "1000", department: str = "IT") -> RawRequest:
    return RawRequest(
        code=code,
        title="t",
        department=department,
        budget=Decimal(budget),
        requestedBy="alex.demo@contoso.com",
    )


@pytest.mark.parametrize(
    ("cents", "route"),
    [
        (1, Route.TEAM_LEAD),
        (4_999_999, Route.TEAM_LEAD),
        (5_000_000, Route.FINANCE),
        (24_999_999, Route.FINANCE),
        (25_000_000, Route.BOARD),
    ],
)
def test_route_boundaries(cents: int, route: Route) -> None:
    assert digest.route_for(cents) is route


def test_validate_returns_the_two_outcome_shapes() -> None:
    assert isinstance(digest.validate(raw(budget="10")), Accepted)
    assert digest.validate(raw("PR-9", "0")) == Rejected("PR-9", "budget must be greater than zero")
    assert isinstance(digest.validate(raw(budget="-5")), Rejected)


def test_department_is_trimmed_and_upper_cased() -> None:
    outcome = digest.validate(raw(department=" hr "))
    assert isinstance(outcome, Accepted)
    assert outcome.request.department == "HR"


def test_request_is_frozen_and_slotted() -> None:
    request = digest.Request("PR-1", "t", "IT", 100)
    with pytest.raises(AttributeError):
        request.cents = 5  # type: ignore[misc]
    assert not hasattr(request, "__dict__")


def test_count_by_generic_helper() -> None:
    assert digest.count_by(["a", "bb", "cc"], len) == {1: 1, 2: 2}


def test_money_formatting() -> None:
    assert digest.money(132_037_075) == "1,320,370.75"
    assert digest.money(5) == "0.05"


def test_json_floats_stay_exact_with_decimal() -> None:
    raws = digest.load(ROOT / "samples" / "requests.json")
    cents = {r["code"]: digest.to_cents(r["budget"]) for r in raws}
    assert cents["PR-2026-0202"] == 4_999_999
    assert cents["PR-2026-0203"] == 5_000_001


def test_deprecated_float_helper_warns() -> None:
    with pytest.warns(DeprecationWarning, match="floats cannot hold"):
        digest.to_cents_float(1.0)


def test_float_conversion_really_is_wrong_for_some_values() -> None:
    # 0.29 * 100 is 28.999999999999996 in binary floating point: truncation loses a cent.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert digest.to_cents_float(0.29) == 28
    assert digest.to_cents(Decimal("0.29")) == 29


def test_batches_keep_order_and_last_batch_is_short() -> None:
    raws = [raw(f"PR-{i}") for i in range(1, 10)]
    result = digest.build_digest(raws)
    assert [len(b) for b in result.batches] == [4, 4, 1]
    assert result.batches[0] == ("PR-1", "PR-2", "PR-3", "PR-4")


def test_sample_digest_matches_the_shared_golden_file() -> None:
    raws = digest.load(ROOT / "samples" / "requests.json")
    golden = (ROOT / "expected" / "digest.txt").read_text(encoding="utf-8")
    assert digest.render(digest.build_digest(raws)) == golden


def test_cli_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert digest.main([]) == 2
    assert "usage" in capsys.readouterr().err
