import json

import pytest

from conftest import GOOD, Wire, gm_call, gm_resp, oa_call, oa_resp
from llm_sidebyside import gemini_adapter as gm
from llm_sidebyside import openai_adapter as oa
from llm_sidebyside.errors import Failure


# ---- extract ------------------------------------------------------------------------------------------------------

def test_openai_extract_sends_strict_schema_and_parses():
    wire = Wire((200, oa_resp(json.dumps(GOOD))))
    out = oa.run_extract(wire.openai())
    sent = wire.requests[0]
    assert sent["url"].endswith("/v1/responses")
    assert sent["headers"]["authorization"] == "Bearer sk-test"
    fmt = sent["body"]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and sent["body"]["store"] is False
    assert out.ok and out.parsed["total_yearly_cost_eur"] == 45000
    assert (out.usage.input_tokens, out.usage.output_tokens, out.usage.reasoning_tokens) == (100, 40, 10)


def test_gemini_extract_sends_response_format_and_parses():
    wire = Wire((200, gm_resp(json.dumps(GOOD))))
    out = gm.run_extract(wire.gemini())
    sent = wire.requests[0]
    assert sent["url"].endswith("/v1/interactions")
    assert "g-test" in json.dumps(sent["headers"])
    assert sent["body"]["response_format"]["mime_type"] == "application/json" and sent["body"]["store"] is False
    assert out.ok and out.parsed["first_to_renew"] == "Litware Security"


@pytest.mark.parametrize("make", [
    lambda t: (oa, lambda w: w.openai(), oa_resp(t)),
    lambda t: (gm, lambda w: w.gemini(), gm_resp(t)),
])
def test_extract_validates_what_the_api_does_not(make):
    bad = dict(GOOD, first_to_renew="", total_yearly_cost_eur=1)
    mod, client, body = make(json.dumps(bad))
    wire = Wire((200, body))
    out = mod.run_extract(client(wire))
    assert out.status == "complete" and not out.ok and out.problems


def test_extract_non_json_is_a_problem_not_a_crash():
    out = oa.run_extract(Wire((200, oa_resp("here you go: {"))).openai())
    assert any("not JSON" in p for p in out.problems)


# ---- truncation and refusal: same idea, different signals ----------------------------------------------------------

def test_openai_truncation_is_status_incomplete_and_reasoning_counts():
    body = oa_resp("Fabrikam Cloud is", status="incomplete", incomplete={"reason": "max_output_tokens"}, usage=(50, 16, 16, 0))
    wire = Wire((200, body))
    out = oa.run_truncate(wire.openai())
    assert wire.requests[0]["body"]["max_output_tokens"] == 16
    assert out.status == "truncated" and out.usage.reasoning_tokens == 16 and out.usage.output_tokens == 16


def test_gemini_truncation_is_status_incomplete_and_thoughts_are_extra():
    wire = Wire((200, gm_resp("Fabrikam", status="incomplete", usage=(50, 4, 12, 0))))
    out = gm.run_truncate(wire.gemini())
    assert wire.requests[0]["body"]["generation_config"] == {"max_output_tokens": 16}
    assert out.status == "truncated"
    assert out.usage.billable_output("gemini") == 16 and out.usage.billable_output("openai") == 4


def test_openai_refusal_is_its_own_status():
    out = oa.run_extract(Wire((200, oa_resp(refusal="I can't help with that."))).openai())
    assert out.status == "refused" and out.text.startswith("I can't")


# ---- tool loops ---------------------------------------------------------------------------------------------------

def test_openai_tool_loop_is_stateless_and_returns_call_output(data):
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"}
    wire = Wire((200, oa_resp(items=[reasoning, oa_call({"within_days": 180})])), (200, oa_resp("Two contracts, 30,900 euros.")))
    out = oa.run_tool(wire.openai(), "gpt-6.2-sol", data)
    second = wire.requests[1]["body"]["input"]
    assert [i.get("type", i.get("role")) for i in second] == ["developer", "user", "reasoning", "function_call", "function_call_output"]
    assert second[2]["encrypted_content"] == "enc"
    result = json.loads(second[-1]["output"])
    assert [r["vendor"] for r in result] == ["Litware Security", "Fabrikam Cloud"]
    assert out.ok and out.requests == 2 and out.tool_calls == ["get_vendor_renewals"]
    assert out.usage.input_tokens == 200


def test_gemini_tool_loop_resends_steps_and_answers_with_function_result(data):
    wire = Wire((200, gm_resp(steps=[gm_call({"within_days": 180})], status="requires_action")), (200, gm_resp("Two contracts.")))
    out = gm.run_tool(wire.gemini(), "gemini-3.8-flash", data)
    second = wire.requests[1]["body"]["input"]
    assert [s["type"] for s in second] == ["user_input", "function_call", "function_result"]
    assert second[-1]["call_id"] == "fc1" and second[-1]["is_error"] is False
    assert json.loads(second[-1]["result"])[0]["vendor"] == "Litware Security"
    assert out.ok and out.requests == 2


def test_bad_tool_arguments_come_back_as_an_error_result_not_an_exception(data):
    wire = Wire((200, oa_resp(items=[oa_call({"within_days": 5000})])), (200, oa_resp("Sorry, I used a bad window.")))
    out = oa.run_tool(wire.openai(), "m", data)
    assert "error" in json.loads(wire.requests[1]["body"]["input"][-1]["output"])
    assert out.ok


def test_tool_loop_gives_up_after_max_turns(data):
    replies = [(200, oa_resp(items=[oa_call({"within_days": 30})]))] * 3
    out = oa.run_tool(Wire(*replies).openai(), "m", data, max_turns=3)
    assert out.status == "failed" and "3 turns" in out.problems[0]


# ---- errors -------------------------------------------------------------------------------------------------------

def test_openai_insufficient_quota_is_not_retried():
    err = {"error": {"message": "You exceeded your current quota", "type": "insufficient_quota", "code": "insufficient_quota"}}
    wire = Wire((429, err))
    with pytest.raises(Failure) as e:
        oa.run_truncate(wire.openai())
    assert e.value.kind == "quota" and not e.value.retryable and len(wire.requests) == 1


def test_rate_limit_is_retried_and_honours_retry_after(monkeypatch):
    slept = []
    monkeypatch.setattr("llm_sidebyside.errors.time.sleep", slept.append)
    wire = Wire((429, {"error": {"message": "slow down", "code": "rate_limit_exceeded"}}, {"retry-after": "3"}), (200, oa_resp("ok")))
    out = oa.run_truncate(wire.openai())
    assert out.status == "complete" and slept == [3.0] and len(wire.requests) == 2


def test_gemini_429_is_rate_limit_and_400_is_not_retried(monkeypatch):
    monkeypatch.setattr("llm_sidebyside.errors.time.sleep", lambda s: None)
    wire = Wire(*[(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})] * 3)
    with pytest.raises(Failure) as e:
        gm.run_truncate(wire.gemini())
    assert e.value.kind == "rate_limit" and len(wire.requests) == 3
    wire = Wire((400, {"error": {"code": 400, "message": "bad schema", "status": "INVALID_ARGUMENT"}}))
    with pytest.raises(Failure) as e:
        gm.run_extract(wire.gemini())
    assert e.value.kind == "bad_request" and len(wire.requests) == 1


def test_auth_error_is_classified():
    with pytest.raises(Failure) as e:
        oa.run_truncate(Wire((401, {"error": {"message": "Incorrect API key", "code": "invalid_api_key"}})).openai())
    assert e.value.kind == "auth" and "sk-test" not in str(e.value)
