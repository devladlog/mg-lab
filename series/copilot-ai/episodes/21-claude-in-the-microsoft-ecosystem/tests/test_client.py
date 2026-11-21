import pytest

from claude_ms.client import ConfigError, ENTRA_SCOPE, build_client, resolve_resource
from conftest import Script, message, text


def test_resource_from_env_and_validation():
    assert resolve_resource(None, env={"ANTHROPIC_FOUNDRY_RESOURCE": "mglabfoundry21"}) == "mglabfoundry21"
    with pytest.raises(ConfigError):
        resolve_resource(None, env={})
    for bad in ("https://x.services.ai.azure.com", "x.services.ai.azure.com", "a/b", "-x"):
        with pytest.raises(ConfigError):
            resolve_resource(bad, env={})


def test_api_key_request_shape():
    s = Script([(200, message([text("ok")]))])
    from claude_ms.client import build_client
    import httpx2 as httpx

    client, conn = build_client("contoso-foundry", api_key="k-test", env={},
                                http_client=httpx.Client(transport=httpx.MockTransport(s)))
    assert conn.auth == "api-key"
    client.messages.create(model="claude-sonnet-5-5", max_tokens=5, messages=[{"role": "user", "content": "hi"}])
    url, headers, body = s.seen[0]
    assert url == "https://contoso-foundry.services.ai.azure.com/anthropic/v1/messages"
    assert headers["x-api-key"] == "k-test"
    assert body["model"] == "claude-sonnet-5-5"  # the deployment name


def test_entra_token_goes_in_bearer_header():
    s = Script([(200, message([text("ok")]))])
    client = s.client(token_provider=lambda: "entra-token")
    client.messages.create(model="d", max_tokens=5, messages=[{"role": "user", "content": "hi"}])
    assert s.seen[0][1]["authorization"] == "Bearer entra-token"
    assert "x-api-key" not in s.seen[0][1]


def test_default_is_entra_with_the_foundry_scope(monkeypatch):
    import azure.identity as ai

    calls = {}
    monkeypatch.setattr(ai, "DefaultAzureCredential", lambda: "cred")
    monkeypatch.setattr(ai, "get_bearer_token_provider", lambda cred, scope: calls.update(cred=cred, scope=scope) or (lambda: "t"))
    client, conn = build_client("contoso-foundry", env={})
    assert conn.auth == "entra" and calls == {"cred": "cred", "scope": ENTRA_SCOPE}
    assert ENTRA_SCOPE == "https://ai.azure.com/.default"


def test_key_from_environment():
    _, conn = build_client("contoso-foundry", env={"ANTHROPIC_FOUNDRY_API_KEY": "x"})
    assert conn.auth == "api-key"
