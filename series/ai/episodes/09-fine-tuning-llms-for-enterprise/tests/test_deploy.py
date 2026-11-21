import json

import pytest

from fttriage import deploy

MODEL = "gpt-4.1-mini-2025-04-14.ft-" + "b" * 32
SUB = "00000000-0000-0000-0000-000000000000"


def call(stub, **kw):
    args = dict(token="tok", subscription=SUB, group="rg-mglab-ai-09", account="mglab-ft-aoai-x", name="triage-ft",
                model_id=MODEL, management=stub.url, poll_seconds=0, sleep=lambda s: None)
    args.update(kw)
    return deploy.deploy(**args)


def test_put_body_and_url_follow_learns_example(stub):
    out = call(stub)
    put = stub.last("PUT", "/deployments/triage-ft")
    assert put["path"] == (f"/subscriptions/{SUB}/resourceGroups/rg-mglab-ai-09/providers/"
                           "Microsoft.CognitiveServices/accounts/mglab-ft-aoai-x/deployments/triage-ft")
    assert put["query"] == "api-version=2025-07-01-preview" and put["auth"] == "Bearer tok"
    assert json.loads(put["body"]) == {"sku": {"name": "DeveloperTier", "capacity": 50},
                                       "properties": {"model": {"format": "OpenAI", "name": MODEL, "version": "1"}}}
    assert out["properties"]["provisioningState"] == "Succeeded" and stub.arm_polls == 2


def test_checkpoints_can_be_deployed_too(stub):
    call(stub, model_id="ftchkpt-" + "c" * 32)
    assert json.loads(stub.last("PUT", "/deployments/triage-ft")["body"])["properties"]["model"]["name"].startswith("ftchkpt-")


def test_bad_inputs_are_refused_before_any_request(stub):
    for kw in ({"sku": "Developer"}, {"name": "bad name!"}, {"model_id": "gpt-4.1-mini"}):
        with pytest.raises(ValueError):
            call(stub, **kw)
    assert stub.requests == []                                  # a base model name must never reach this path


def test_failed_provisioning_and_http_errors_are_raised(stub):
    stub.arm_states = ["Creating", "Failed"]
    with pytest.raises(RuntimeError, match="Failed"):
        call(stub)
    stub.arm_put_status = 403
    with pytest.raises(RuntimeError, match="403"):
        call(stub)


def test_timeout(stub):
    stub.arm_states = ["Creating"]
    with pytest.raises(TimeoutError):
        call(stub, timeout_seconds=-1)


def test_delete(stub):
    deploy.delete("tok", SUB, "rg", "acc", "triage-ft", management=stub.url)
    r = stub.last("DELETE", "/deployments/triage-ft")
    assert r["query"] == "api-version=2025-07-01-preview" and r["auth"] == "Bearer tok"


def test_get_token_uses_the_management_scope():
    from conftest import FakeCredential
    c = FakeCredential()
    assert deploy.get_token(c) == "fake-entra-token" and c.scopes == ["https://management.azure.com/.default"]
