"""The real OpenAI SDK against a local stub that behaves like the gateway (no Azure needed)."""
import pytest

pytest.importorskip("openai")

from aoai_gateway.client import UNUSED_BEARER, gateway_base_url, make_gateway_client  # noqa: E402
from aoai_gateway.smoke import Row, main, run_burst  # noqa: E402
from aoai_gateway.usage import Ledger  # noqa: E402


def ok(total=23):
    return {"id": "c", "object": "chat.completion", "created": 0, "model": "gpt-5-mini-2025-08-07",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": total - 13, "total_tokens": total}}


def test_base_url_shape():
    assert gateway_base_url("https://contoso-gw.azure-api.net/") == "https://contoso-gw.azure-api.net/aoai/openai/v1/"


def test_client_sends_the_subscription_key_header_to_the_proxied_v1_path(stub_server):
    stub_server.responses.append((200, {}, ok()))
    client = make_gateway_client(stub_server.url, "team-key-123", max_retries=0)
    client.chat.completions.create(model="chat", messages=[{"role": "user", "content": "hi"}])
    req = stub_server.requests[0]
    assert req["path"] == "/aoai/openai/v1/chat/completions"
    assert req["headers"]["api-key"] == "team-key-123"
    assert req["headers"]["authorization"] == f"Bearer {UNUSED_BEARER}"   # overwritten by the gateway policy
    assert req["body"]["model"] == "chat"


def test_client_refuses_an_empty_key():
    with pytest.raises(ValueError, match="subscription_key"):
        make_gateway_client("https://x.azure-api.net", "")


def test_burst_shows_budget_then_429_then_403(stub_server):
    stub_server.responses += [
        (200, {"x-gateway-remaining-tokens": "1700", "x-gateway-tokens-consumed": "300"}, ok(300)),
        (200, {"x-gateway-remaining-tokens": "1400", "x-gateway-tokens-consumed": "300"}, ok(300)),
        (429, {"retry-after": "41"}, {"statusCode": 429, "message": "Token limit is exceeded."}),
        (403, {}, {"statusCode": 403, "message": "Token quota is exceeded."}),
    ]
    client = make_gateway_client(stub_server.url, "k", max_retries=0)
    ledger = Ledger()
    rows = run_burst(client, "chat", 4, ledger)
    assert [(r.status, r.kind) for r in rows] == [(200, "ok"), (200, "ok"), (429, "throttled"),
                                                   (403, "quota_exhausted")]
    assert rows[1].remaining == 1400 and rows[2].retry_after_s == 41.0
    assert ledger.totals["smoke"]["total_tokens"] == 600 and ledger.last_remaining == 1400
    assert str(rows[2]) == "#03  429  throttled    retry-after=41s"
    assert "remaining-this-minute=1700" in str(rows[0])


def test_sdk_retry_on_top_of_gateway_multiplies_calls(stub_server):
    # max_retries=2 (SDK default): one logical call can become three HTTP calls to the gateway.
    stub_server.responses += [(429, {"retry-after-ms": "10"}, {}), (429, {"retry-after-ms": "10"}, {}),
                              (429, {"retry-after-ms": "10"}, {})]
    client = make_gateway_client(stub_server.url, "k", max_retries=2)
    rows = run_burst(client, "chat", 1, Ledger())
    assert rows[0].kind == "throttled" and len(stub_server.requests) == 3


def test_cli_needs_gateway_and_key(monkeypatch):
    monkeypatch.delenv("APIM_SUBSCRIPTION_KEY", raising=False)
    monkeypatch.delenv("APIM_GATEWAY_URL", raising=False)
    assert main([]) == 2


def test_row_formatting_without_retry_after():
    assert str(Row(5, 503, "unavailable")) == "#05  503  unavailable"
