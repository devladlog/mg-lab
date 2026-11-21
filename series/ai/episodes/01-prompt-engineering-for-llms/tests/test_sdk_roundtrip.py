"""Runs the real OpenAI Python SDK against a local stub of the Azure OpenAI v1 endpoint (no cloud needed)."""
import json

import pytest

pytest.importorskip("openai")

from triage.evaluate import make_client, sdk_complete  # noqa: E402
from triage.prompts import get_prompt  # noqa: E402
from triage.request import build_request  # noqa: E402

ANSWER = {"category": "network", "priority": "P1", "summary": "Sales team cannot connect to VPN.",
          "needs_human": True, "injection_suspected": False}


def completion(content, refusal=None, finish="stop"):
    return {
        "id": "chatcmpl-0", "object": "chat.completion", "created": 0, "model": "gpt-5-mini-2025-08-07",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "refusal": refusal}}],
        "usage": {"prompt_tokens": 812, "completion_tokens": 64, "total_tokens": 876},
    }


def test_request_reaches_the_v1_endpoint_with_a_bearer_token(stub_server):
    stub_server.responses.append((200, {}, completion(json.dumps(ANSWER))))
    client = make_client(stub_server.url, token_provider=lambda: "fake-entra-token", max_retries=0)
    body = build_request(get_prompt("v2"), "VPN down for sales", deployment="triage-mini", model="gpt-5-mini")

    content, usage, finish = sdk_complete(client)(body)

    req = stub_server.requests[0]
    assert req["path"] == "/openai/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer fake-entra-token"
    assert req["body"]["model"] == "triage-mini"
    assert req["body"]["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in req["body"]
    assert json.loads(content) == ANSWER and usage["prompt_tokens"] == 812 and finish == "stop"


def test_sdk_retries_429_using_retry_after(stub_server):
    stub_server.responses += [(429, {"retry-after-ms": "50"}, {"error": {"code": "429", "message": "rate"}}),
                              (200, {}, completion(json.dumps(ANSWER)))]
    client = make_client(stub_server.url, token_provider=lambda: "t", max_retries=2)
    body = build_request(get_prompt("v2"), "x", deployment="triage-mini", model="gpt-5-mini")
    content, _, _ = sdk_complete(client)(body)
    assert len(stub_server.requests) == 2 and json.loads(content)["priority"] == "P1"


def test_refusal_becomes_no_content(stub_server):
    stub_server.responses.append((200, {}, completion(None, refusal="I can't help with that.")))
    client = make_client(stub_server.url, token_provider=lambda: "t", max_retries=0)
    content, _, _ = sdk_complete(client)(build_request(get_prompt("v2"), "x", deployment="d", model="gpt-5-mini"))
    assert content is None
