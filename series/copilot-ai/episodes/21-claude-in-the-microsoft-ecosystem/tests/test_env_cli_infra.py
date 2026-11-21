import json
import shutil
import subprocess

import pytest

from claude_ms.claude_code_env import build_env, render
from claude_ms.cli import main
from conftest import ROOT


def test_env_variables_match_learn():
    env = build_env("mglabfoundry21", {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"})
    assert env == {
        "CLAUDE_CODE_USE_FOUNDRY": "1",
        "ANTHROPIC_FOUNDRY_RESOURCE": "mglabfoundry21",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5",
    }


def test_env_rejects_urls_unknown_families_and_shell_metacharacters():
    with pytest.raises(Exception):
        build_env("https://x.services.ai.azure.com")
    with pytest.raises(ValueError):
        build_env("r", {"gpt": "x"})
    with pytest.raises(ValueError):
        build_env("r", {"sonnet": 'x"; rm -rf /'})


def test_render_shells_and_never_writes_a_key():
    env = build_env("r", {"opus": "claude-opus-5-5"})
    ps, sh = render(env, "powershell"), render(env, "bash")
    assert '$env:CLAUDE_CODE_USE_FOUNDRY = "1"' in ps and 'export CLAUDE_CODE_USE_FOUNDRY="1"' in sh
    assert "API_KEY" not in ps.replace("ANTHROPIC_FOUNDRY_API_KEY", "") and "az login" in ps
    with pytest.raises(ValueError):
        render(env, "cmd")


def test_cli_code_env(capsys):
    assert main(["code-env", "--resource", "r1", "--shell", "bash", "--sonnet", "s1"]) == 0
    out = capsys.readouterr().out
    assert 'export ANTHROPIC_DEFAULT_SONNET_MODEL="s1"' in out


def test_cli_reports_config_errors(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_RESOURCE", raising=False)
    assert main(["triage", "--deployment", "d"]) == 2
    assert "resource name missing" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("bicep") is None, reason="bicep CLI not installed")
def test_bicep_builds_and_carries_the_attestation():
    infra = ROOT / "src" / "infra"
    out = subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--stdout"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    tpl = json.loads(out.stdout)
    dep = [r for r in tpl["resources"] if r["type"].endswith("/deployments")][0]
    assert dep["properties"]["model"]["format"] == "Anthropic"
    assert set(dep["properties"]["modelProviderData"]) == {"organizationName", "countryCode", "industry"}
    assert dep["sku"]["name"] == "GlobalStandard"
    acct = [r for r in tpl["resources"] if r["type"] == "Microsoft.CognitiveServices/accounts"][0]
    assert acct["properties"]["disableLocalAuth"] == "[parameters('disableLocalAuth')]"
    params = subprocess.run(["bicep", "build-params", str(infra / "main.bicepparam"), "--stdout"], capture_output=True, text=True)
    assert params.returncode == 0, params.stderr
    p = json.loads(json.loads(params.stdout)["parametersJson"])["parameters"]
    assert [d["name"] for d in p["deployments"]["value"]] == ["claude-sonnet-5-5", "claude-haiku-5-5"]
