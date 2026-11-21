import pytest

from claude_ms.fallback import ask_with_fallback
from conftest import Script, message, text

ERR429 = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}})
ERR500 = (500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})
ERR404 = (404, {"type": "error", "error": {"type": "not_found_error", "message": "deployment not found"}})
OK = (200, message([text("answer")], inp=7, out=3))


def test_rate_limit_moves_to_next_deployment_without_sdk_retries():
    s = Script([ERR429, OK])
    res = ask_with_fallback(s.client(), ["claude-sonnet-5-5", "claude-haiku-5-5"], "hi")
    assert res.deployment == "claude-haiku-5-5" and res.text == "answer"
    assert res.skipped == [("claude-sonnet-5-5", "RateLimitError")]
    assert [b["model"] for _, _, b in s.seen] == ["claude-sonnet-5-5", "claude-haiku-5-5"]  # exactly one try each


def test_server_error_also_falls_over():
    s = Script([ERR500, OK])
    assert ask_with_fallback(s.client(), ["a", "b"], "hi").deployment == "b"


def test_wrong_deployment_name_is_not_hidden():
    import anthropic

    s = Script([ERR404])
    with pytest.raises(anthropic.NotFoundError):
        ask_with_fallback(s.client(), ["typo", "b"], "hi")
    assert len(s.seen) == 1


def test_all_failed_raises_with_reasons():
    s = Script([ERR429, ERR500])
    with pytest.raises(RuntimeError) as e:
        ask_with_fallback(s.client(), ["a", "b"], "hi")
    assert "a: RateLimitError" in str(e.value) and "b: InternalServerError" in str(e.value)


def test_needs_a_deployment():
    with pytest.raises(ValueError):
        ask_with_fallback(Script([]).client(), [], "hi")


def test_system_prompt_is_passed():
    s = Script([OK])
    ask_with_fallback(s.client(), ["a"], "hi", system="be brief")
    assert s.seen[0][2]["system"] == "be brief"
