import json

import pytest
from jsonschema import validate

from triage.prompts import FEW_SHOT, get_prompt
from triage.request import build_request, is_reasoning_model
from triage.schema import TRIAGE_SCHEMA
from triage.spotlight import OPEN_TAG


def test_v1_is_a_single_user_message_without_schema():
    p = get_prompt("v1")
    msgs = p.build_messages("printer jam")
    assert [m["role"] for m in msgs] == ["user"]
    assert p.response_format is None


def test_v2_has_system_then_few_shot_pairs_then_the_ticket():
    msgs = get_prompt("v2").build_messages("printer jam")
    roles = [m["role"] for m in msgs]
    assert roles == ["system"] + ["user", "assistant"] * len(FEW_SHOT) + ["user"]
    assert msgs[-1]["content"] == f"{OPEN_TAG}printer^jam<</TICKET>>"


@pytest.mark.parametrize("text,answer", FEW_SHOT)
def test_few_shot_answers_match_the_output_schema(text, answer):
    validate(answer, TRIAGE_SCHEMA)


@pytest.mark.parametrize("model,expected", [("gpt-5-mini", True), ("o4-mini", True), ("gpt-4.1-mini", False)])
def test_reasoning_model_detection(model, expected):
    assert is_reasoning_model(model) is expected


def test_reasoning_request_drops_temperature_and_uses_max_completion_tokens():
    body = build_request(get_prompt("v2"), "x", deployment="triage-mini", model="gpt-5-mini")
    assert body["model"] == "triage-mini"
    assert "temperature" not in body and "max_tokens" not in body
    assert body["max_completion_tokens"] == 2000 and body["reasoning_effort"] == "low"
    assert body["response_format"]["json_schema"]["strict"] is True


def test_classic_request_uses_temperature_zero_and_max_tokens():
    body = build_request(get_prompt("v2"), "x", deployment="d", model="gpt-4.1-mini")
    assert body["temperature"] == 0 and body["max_tokens"] == 2000
    assert "reasoning_effort" not in body


def test_unknown_prompt_version():
    with pytest.raises(ValueError, match="Known: v1, v2"):
        get_prompt("v9")


def test_request_is_json_serialisable():
    json.dumps(build_request(get_prompt("v2"), "x", deployment="d", model="gpt-5-mini"))
