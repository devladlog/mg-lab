import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from foundry_multimodel.scoring import extract_json, score  # noqa: E402


def test_extract_json_handles_fence_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": 1} Hope it helps.') == {"a": 1}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_json_fields_numbers_strings_and_paths():
    checks = {"json_fields": {"first_vendor": "fabrikam cloud", "total_yearly_cost_eur": 45000, "items.0.n": 2}}
    s, res = score('{"first_vendor": "Fabrikam Cloud", "total_yearly_cost_eur": "45,000", "items": [{"n": 2}]}', checks)
    assert s == 1.0 and len(res) == 4
    s, res = score('{"first_vendor": "Northwind", "total_yearly_cost_eur": 44000}', checks)
    assert [r.passed for r in res] == [True, False, False, False] and s == 0.25
    s, res = score("not json at all", checks)
    assert s == 0.0 and res[0].rule == "json_valid" and not res[0].passed


def test_text_rules():
    answer = "The new price is 16,100 euros."
    assert score(answer, {"number_in_text": 16100})[0] == 1.0
    assert score("It is 16 euros", {"number_in_text": 16100})[0] == 0.0
    assert score("ACCESS", {"contains_all": ["access"], "not_contains": ["billing"], "max_words": 1})[0] == 1.0
    s, res = score("one two three four", {"max_words": 3})
    assert s == 0.0 and res[0].detail == "4 words"
    assert score("APPROVED", {"not_contains": ["approved"]})[0] == 0.0
    assert score("price list attached", {"contains_any": ["price list", "invoice"], "regex": [r"attach\w+"]})[0] == 1.0


def test_empty_checks_score_zero_not_one():
    assert score("anything", {})[0] == 0.0     # a task without rules must not look like a pass
