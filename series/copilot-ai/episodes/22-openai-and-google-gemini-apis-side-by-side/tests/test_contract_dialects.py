import copy

import pytest

from conftest import GOOD
from llm_sidebyside import contract, dialects


def test_tool_returns_soonest_first_within_window(data):
    rows = contract.get_vendor_renewals(data, 180)
    assert [r["vendor"] for r in rows] == ["Litware Security", "Fabrikam Cloud"]


@pytest.mark.parametrize("bad", [0, 731, "30", 1.5, True, None])
def test_tool_rejects_bad_window(data, bad):
    with pytest.raises(ValueError):
        contract.get_vendor_renewals(data, bad)


def test_vendor_file_totals_45000(data):
    assert sum(v["yearly_cost_eur"] for v in data["vendors"]) == 45000


def test_check_extract_accepts_good_answer():
    assert contract.check_extract(GOOD) == []


def test_check_extract_catches_what_neither_api_enforces():
    bad = copy.deepcopy(GOOD)
    bad["first_to_renew"] = ""            # minLength is dropped by OpenAI strict and ignored by Gemini
    assert any("first_to_renew" in p for p in contract.check_extract(bad))
    dup = copy.deepcopy(GOOD)
    dup["vendors"].append(dup["vendors"][0])  # uniqueItems likewise
    assert contract.check_extract(dup)


def test_check_extract_catches_wrong_arithmetic_and_wrong_earliest():
    bad = copy.deepcopy(GOOD)
    bad["total_yearly_cost_eur"] = 44000
    bad["first_to_renew"] = "Fabrikam Cloud"
    problems = contract.check_extract(bad)
    assert any("total_yearly_cost_eur" in p for p in problems)
    assert any("first_to_renew" in p for p in problems)


def test_openai_strict_requires_everything_closes_objects_and_nulls_optionals():
    strict, report = dialects.to_openai_strict(contract.EXTRACT_SCHEMA)
    item = strict["properties"]["vendors"]["items"]
    assert strict["additionalProperties"] is False and item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    assert item["properties"]["notice_days"]["type"] == ["integer", "null"]
    assert report["made_nullable"] == ["vendors[].notice_days"]


def test_openai_strict_reports_dropped_keywords_and_leaves_input_alone():
    before = copy.deepcopy(contract.EXTRACT_SCHEMA)
    strict, report = dialects.to_openai_strict(contract.EXTRACT_SCHEMA)
    assert contract.EXTRACT_SCHEMA == before
    assert ("vendors", "uniqueItems") in report["dropped_keywords"]
    assert "minLength" not in str(strict)


def test_gemini_keeps_schema_and_lists_unenforced_keywords():
    found = dialects.gemini_unenforced(contract.EXTRACT_SCHEMA)
    assert ("vendors[].name", "minLength") in found and ("vendors", "uniqueItems") in found
    body = dialects.gemini_request("m", "sys", "p", schema=contract.EXTRACT_SCHEMA)
    assert body["response_format"] == {"type": "text", "mime_type": "application/json", "schema": contract.EXTRACT_SCHEMA}
    assert "notice_days" not in body["response_format"]["schema"]["properties"]["vendors"]["items"]["required"]


def test_requests_are_stateless_and_put_instructions_in_each_vendors_slot():
    o = dialects.openai_request("m", "SYS", "P")
    g = dialects.gemini_request("m", "SYS", "P")
    assert o["store"] is False and g["store"] is False
    assert o["input"][0] == {"role": "developer", "content": "SYS"} and "instructions" not in o
    assert g["system_instruction"] == "SYS" and g["input"][0]["type"] == "user_input"


def test_token_limit_is_named_differently():
    o = dialects.openai_request("m", "s", "p", max_output_tokens=16)
    g = dialects.gemini_request("m", "s", "p", max_output_tokens=16)
    assert o["max_output_tokens"] == 16 and g["generation_config"] == {"max_output_tokens": 16}


def test_tool_shapes_differ_by_strict_flag_only_in_openai():
    o = dialects.openai_tool(contract.TOOL_SPEC)
    g = dialects.gemini_tool(contract.TOOL_SPEC)
    assert o["strict"] is True and "strict" not in g
    assert o["parameters"]["additionalProperties"] is False and "additionalProperties" not in g["parameters"]
    assert dialects.openai_request("m", "s", "p", tool=contract.TOOL_SPEC)["include"] == ["reasoning.encrypted_content"]
