import json

import pytest

from five_ais import providers as P
from five_ais.http import ApiError, is_local_url


class Rec:
    """Records the (url, payload, headers) the adapter sends and returns a canned vendor response."""
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append((url, payload, headers))
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "sk-test-SECRET")


def test_build_prompt_modes():
    assert P.build_prompt("RULES", "Q", "inline") == (None, "RULES\n\nQ")
    assert P.build_prompt("RULES", "Q", "system") == ("RULES", "Q")
    with pytest.raises(ValueError):
        P.build_prompt("R", "Q", "other")


def test_openai_request_and_response_shape():
    t = Rec({"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": "Hello "}, {"type": "output_text", "text": "world"}]}],
        "usage": {"input_tokens": 12, "output_tokens": 34}})
    p = P.build({"id": "gpt", "kind": "openai", "model": "m1", "api_key_env": "OPENAI_API_KEY", "max_tokens": 77}, t)
    r = p.ask("SYS", "hi")
    url, body, headers = t.calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert body == {"model": "m1", "input": "hi", "max_output_tokens": 77, "store": False, "instructions": "SYS"}
    assert headers == {"Authorization": "Bearer sk-test-SECRET"}
    assert (r.text, r.input_tokens, r.output_tokens, r.error) == ("Hello world", 12, 34, "")
    assert r.seconds is not None


def test_openai_incomplete_status_is_an_error_not_a_silent_short_answer():
    t = Rec({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []})
    r = P.build({"id": "g", "kind": "openai", "model": "m", "api_key_env": "OPENAI_API_KEY"}, t).ask(None, "hi")
    assert "incomplete" in r.error and "max_output_tokens" in r.error


def test_anthropic_headers_version_and_no_temperature():
    t = Rec({"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "Hi"}], "stop_reason": "end_turn",
             "usage": {"input_tokens": 5, "output_tokens": 6}})
    p = P.build({"id": "c", "kind": "anthropic", "model": "m", "api_key_env": "ANTHROPIC_API_KEY"}, t)
    r = p.ask("SYS", "hi")
    url, body, headers = t.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers == {"x-api-key": "sk-test-SECRET", "anthropic-version": "2026-10-21"}
    assert body["max_tokens"] == 1500 and body["system"] == "SYS" and "temperature" not in body
    assert (r.text, r.input_tokens, r.output_tokens) == ("Hi", 5, 6)


def test_anthropic_temperature_rules_follow_the_api_version():
    t = Rec({"content": [{"type": "text", "text": "x"}], "usage": {}})
    new = P.build({"id": "c", "kind": "anthropic", "model": "m", "api_key_env": "ANTHROPIC_API_KEY", "temperature": 0}, t).ask(None, "q")
    assert "removed" in new.error and t.calls == []                     # refused before any request is made
    old = P.build({"id": "c", "kind": "anthropic", "model": "m", "api_key_env": "ANTHROPIC_API_KEY", "temperature": 0,
                   "anthropic_version": "2023-06-01"}, t).ask(None, "q")
    assert old.error == "" and t.calls[0][1]["temperature"] == 0


def test_anthropic_refusal_is_flagged():
    t = Rec({"content": [], "stop_reason": "refusal", "usage": {}})
    r = P.build({"id": "c", "kind": "anthropic", "model": "m", "api_key_env": "ANTHROPIC_API_KEY"}, t).ask(None, "q")
    assert "refus" in r.error


def test_gemini_request_and_response_shape():
    t = Rec({"candidates": [{"content": {"parts": [{"text": "secret thoughts", "thought": True}, {"text": "Answer"}]},
                             "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "thoughtsTokenCount": 20}})
    p = P.build({"id": "g", "kind": "gemini", "model": "gm-1", "api_key_env": "GEMINI_API_KEY", "max_tokens": 99}, t)
    r = p.ask("SYS", "hi")
    url, body, headers = t.calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gm-1:generateContent"
    assert headers == {"x-goog-api-key": "sk-test-SECRET"} and "key=" not in url
    assert body == {"contents": [{"role": "user", "parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 99},
                    "systemInstruction": {"parts": [{"text": "SYS"}]}}
    assert (r.text, r.input_tokens, r.output_tokens) == ("Answer", 10, 24)      # thinking tokens are counted as output


def test_gemini_blocked_prompt_and_empty_candidate():
    blocked = P.build({"id": "g", "kind": "gemini", "model": "m", "api_key_env": "GEMINI_API_KEY"},
                      Rec({"promptFeedback": {"blockReason": "SAFETY"}})).ask(None, "q")
    assert "blocked" in blocked.error
    empty = P.build({"id": "g", "kind": "gemini", "model": "m", "api_key_env": "GEMINI_API_KEY"},
                    Rec({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]})).ask(None, "q")
    assert "MAX_TOKENS" in empty.error


def test_local_provider_uses_chat_completions_and_guards_the_url():
    t = Rec({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
    p = P.build({"id": "l", "kind": "local", "model": "m", "base_url": "http://127.0.0.1:11434/v1"}, t)
    assert p.problems() == []
    r = p.ask(None, "hi")
    assert t.calls[0][0] == "http://127.0.0.1:11434/v1/chat/completions" and t.calls[0][1]["messages"] == [{"role": "user", "content": "hi"}]
    assert (r.text, r.input_tokens, r.output_tokens) == ("ok", 3, 2)
    remote = P.build({"id": "l", "kind": "local", "model": "m", "base_url": "https://api.example.com/v1"})
    assert any("not a local address" in x for x in remote.problems())
    assert is_local_url("http://localhost:1234/v1")


def test_manual_provider(tmp_path):
    f = tmp_path / "answers.json"
    f.write_text(json.dumps({"t1": " pasted answer ", "t2": ""}), encoding="utf-8")
    p = P.build({"id": "copilot", "kind": "manual", "answers_file": "answers.json"}, base_dir=tmp_path)
    assert p.problems() == []
    r = p.ask(None, "q", "t1")
    assert r.text == "pasted answer" and r.seconds is None and r.error == ""
    assert "no manual answer" in p.ask(None, "q", "t2").error and "no manual answer" in p.ask(None, "q", "t3").error
    missing = P.build({"id": "copilot", "kind": "manual", "answers_file": "nope.json"}, base_dir=tmp_path)
    assert missing.problems() and "not found" in missing.problems()[0]


def test_api_errors_become_error_rows_and_never_leak_the_key():
    p = P.build({"id": "g", "kind": "openai", "model": "m", "api_key_env": "OPENAI_API_KEY"},
                Rec(error=ApiError(401, '{"error":"invalid key"}')))
    r = p.ask(None, "q")
    assert r.error.startswith("HTTP 401") and "SECRET" not in r.error and r.text == ""
    conn = P.build({"id": "g", "kind": "openai", "model": "m", "api_key_env": "OPENAI_API_KEY"}, Rec(error=ConnectionError("cannot reach x")))
    assert "ConnectionError" in conn.ask(None, "q").error


def test_missing_key_and_model_placeholders_are_reported(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    p = P.build({"id": "g", "kind": "openai", "model": "REPLACE-me", "api_key_env": "OPENAI_API_KEY"}, Rec({}))
    assert "model not set in config" in p.problems() and "OPENAI_API_KEY not set" in p.problems()
    assert "OPENAI_API_KEY is empty" in p.ask(None, "q").error


def test_unknown_kind():
    with pytest.raises(ValueError, match="unknown provider kind"):
        P.build({"id": "x", "kind": "bard"})
