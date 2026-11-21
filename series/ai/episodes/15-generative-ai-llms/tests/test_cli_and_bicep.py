import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import lp

from llmprobe import cli
from llmprobe.client import SCOPE, make_client

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run(stub, cred, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_client", lambda endpoint, credential=None: make_client(stub.url, credential=cred))

    def go(*args):
        rc = cli.main(list(args))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return go


def test_scope_is_the_foundry_audience(client, stub, cred):
    stub.handler = lambda req: {"content": "x"}
    client.chat.completions.create(model="chat", messages=[{"role": "user", "content": "x"}])
    assert SCOPE in cred.scopes and stub.requests[0]["auth"] == "Bearer fake-entra-token"
    assert stub.requests[0]["path"] == "/openai/v1/chat/completions"


def test_tokens_command_needs_no_endpoint(capsys):
    assert cli.main(["tokens"]) == 0
    assert "total" in capsys.readouterr().out
    assert cli.main(["tokens", "--show", "Tell me about the solar system.", "--encoding", "cl100k_base"]) == 0
    assert "7 tokens" in capsys.readouterr().out


def test_probe_command(run, stub):
    def h(req):
        p = 0.95 if "<<CONTEXT>>" in req["messages"][1]["content"] else 0.5
        return {"content": "C", "logprobs": {"content": [lp("C", math.log(p), [("C", math.log(p)), ("B", math.log(1 - p))])], "refusal": None}}
    stub.handler = h
    rc, out, _ = run("probe", "--endpoint", "https://x", "--deployment", "chat")
    assert rc == 0 and out.count("\n") >= 9
    assert "answer" in out and "escalate" in out


def test_sample_command_exit_code_follows_the_facts(run, stub):
    stub.handler = lambda req: {"content": "You can carry 5 days until 31 March."}
    rc, out, _ = run("sample", "--endpoint", "https://x", "--runs", "2")
    assert rc == 0 and "t=0 no seed" in out and len(stub.requests) == 8
    stub.handler = lambda req: {"content": "You can carry some days."}
    rc, out, _ = run("sample", "--endpoint", "https://x", "--runs", "2")
    assert rc == 1 and "FAIL" in out


def test_stream_command(run, stub):
    stub.handler = lambda req: {"content": "Open the HR portal and send form HR-12.", "completion_tokens": 10}
    rc, out, _ = run("stream", "--endpoint", "https://x", "--runs", "2")
    assert rc == 0 and "streaming: first content" in out and "finish_reason=stop" in out
    assert sum(1 for r in stub.requests if r["json"].get("stream")) == 2 and len(stub.requests) == 4


def test_budget_dry_run_needs_no_endpoint_or_call(run, stub):
    rc, out, _ = run("budget", "--dry-run", "--context-budget", "120")
    assert rc == 0 and "chunks kept 2" in out and "dropped: ## Carry-over" in out and stub.requests == []


def test_budget_real_call_prints_estimate_and_billed(run, stub):
    stub.handler = lambda req: {"content": "Up to 5 days, until 31 March.", "prompt_tokens": 4000, "completion_tokens": 9}
    rc, out, _ = run("budget", "--endpoint", "https://x", "--context-budget", "400")
    assert rc == 0 and "billed prompt tokens: 4,000" in out and "finish_reason=stop" in out
    sent = stub.requests[0]["json"]["messages"][1]["content"]
    assert "## Carry-over" in sent and sent.rstrip().endswith("How many days can I carry over, and until when?")


def test_budget_error_is_exit_2(run):
    rc, _, err = run("budget", "--dry-run", "--max-output", "99999")
    assert rc == 2 and "32,768" in err


def test_reasoning_model_is_refused_before_any_call(run, stub):
    rc, _, err = run("probe", "--endpoint", "https://x", "--model", "gpt-5-mini")
    assert rc == 2 and "reasoning" in err and stub.requests == []


def test_endpoint_is_required(monkeypatch):
    monkeypatch.delenv("LLMPROBE_ENDPOINT", raising=False)
    with pytest.raises(SystemExit):
        cli.main(["sample"])


@pytest.fixture(scope="module")
def arm():
    if not shutil.which("bicep"):
        pytest.skip("bicep CLI not installed")
    out = subprocess.run(["bicep", "build", str(ROOT / "infra/main.bicep"), "--stdout"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_bicep_is_keyless_and_deploys_one_pinned_standard_model(arm):
    res = arm["resources"]
    acct = next(r for r in res if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acct["properties"]["disableLocalAuth"] is True and acct["kind"] == "OpenAI"
    deps = [r for r in res if r["type"].endswith("/deployments")]
    assert len(deps) == 1 and deps[0]["sku"]["name"] == "Standard"
    assert deps[0]["properties"]["model"]["name"] == "[parameters('model')]"
    assert arm["parameters"]["model"]["defaultValue"] == "gpt-4.1-mini" and arm["parameters"]["modelVersion"]["defaultValue"] == "2025-04-14"
    assert deps[0]["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    roles = [r for r in res if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(roles) == 1 and arm["variables"]["openAiUser"] == "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


def test_bicepparam_uses_a_zero_guid():
    assert "00000000-0000-0000-0000-000000000000" in (ROOT / "infra/main.bicepparam").read_text()
