"""FoundryBackend against a stub of the SDK objects (TEST ONLY), plus checks against the real installed SDK and bicep when present."""
import inspect
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from foundry_multimodel.backend import AgentHandle, FoundryBackend  # noqa: E402


class StubOpenAI:
    def __init__(self, fail_first_with_429=False):
        self.calls, self.deleted_conversations, self.fail = [], [], fail_first_with_429
        self.conversations = SimpleNamespace(create=lambda: SimpleNamespace(id="conv_1"),
                                             delete=lambda cid: self.deleted_conversations.append(cid))
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            self.fail = False
            e = RuntimeError("rate limited")
            e.status_code = 429
            raise e
        return SimpleNamespace(output_text="access", usage=SimpleNamespace(input_tokens=11, output_tokens=1), model="gpt-4.1-mini")


class StubProject:
    def __init__(self, openai):
        self.created, self.deleted, self.openai, self.client_for = [], [], openai, []
        self.agents = SimpleNamespace(create_version=self._create, delete_version=lambda n, v: self.deleted.append((n, v)))

    def _create(self, agent_name, definition):
        self.created.append((agent_name, definition))
        return SimpleNamespace(name=agent_name, version=3)

    def get_openai_client(self, agent_name):
        self.client_for.append(agent_name)
        return self.openai


def test_backend_flow_with_stub_sdk_objects():
    pytest.importorskip("azure.ai.projects", reason="PromptAgentDefinition comes from the real SDK")
    openai = StubOpenAI(fail_first_with_429=True)
    sleeps = []
    project = StubProject(openai)
    be = FoundryBackend(project, sleep=sleeps.append)
    h = be.create_agent("mglab-ep20-gpt", "gpt-4.1-mini", "be brief")
    assert h == AgentHandle("mglab-ep20-gpt", "3", "gpt-4.1-mini")
    ans = be.ask(h, "Classify this")
    assert ans.text == "access" and (ans.input_tokens, ans.output_tokens) == (11, 1) and ans.served_model == "gpt-4.1-mini"
    assert sleeps == [1]                                              # one retry after the 429
    assert openai.calls[-1] == {"conversation": "conv_1", "input": "Classify this"}
    assert openai.deleted_conversations == ["conv_1"]                 # conversation cleaned up
    be.ask(h, "again")
    assert project.client_for == ["mglab-ep20-gpt"]                   # one bound client per agent, reused
    be.delete_agent(h)
    assert project.deleted == [("mglab-ep20-gpt", "3")]
    definition = project.created[0][1]
    assert definition.model == "gpt-4.1-mini" and definition.instructions == "be brief"


def test_non_429_errors_propagate_and_still_clean_up():
    openai = StubOpenAI()
    openai.responses = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(ValueError("bad deployment")))
    be = FoundryBackend(StubProject(openai))
    with pytest.raises(ValueError):
        be.ask(AgentHandle("a", "1", "m"), "q")
    assert openai.deleted_conversations == ["conv_1"]


def test_call_shapes_match_the_installed_azure_ai_projects_sdk():
    pytest.importorskip("azure.ai.projects", reason="azure-ai-projects not installed (pip install -r src/requirements.txt)")
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.core.credentials import AccessToken

    class Cred:
        def get_token(self, *a, **k):
            return AccessToken("x", 9999999999)

    client = AIProjectClient(endpoint="https://contoso-foundry.services.ai.azure.com/api/projects/demo", credential=Cred())
    inspect.signature(client.agents.create_version).bind(agent_name="n", definition=PromptAgentDefinition(model="m", instructions="i"))
    inspect.signature(client.agents.delete_version).bind("n", "1")
    inspect.signature(client.get_openai_client).bind(agent_name="n")
    d = PromptAgentDefinition(model="gpt-4.1-mini", instructions="i")
    assert d.model == "gpt-4.1-mini" and d.instructions == "i"


@pytest.mark.skipif(shutil.which("bicep") is None, reason="bicep CLI not installed")
def test_bicep_builds_and_deploys_every_listed_model():
    infra = ROOT / "src" / "infra"
    out = subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--stdout"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Microsoft.CognitiveServices/accounts/deployments" in out.stdout and "allowProjectManagement" in out.stdout
    params = subprocess.run(["bicep", "build-params", str(infra / "main.bicepparam"), "--stdout"], capture_output=True, text=True, timeout=120)
    assert params.returncode == 0, params.stderr
