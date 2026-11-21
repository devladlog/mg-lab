import json
from pathlib import Path

import pytest

from flowkit import run_flow
from mockgraph import MockGraph

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
SAMPLES = ROOT / "src" / "samples"
OK = {"status": "Succeeded", "body": {}}


def sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def flow():
    (path,) = (SOLUTION / "Workflows").glob("Userswithoutamanager-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def actions(flow):
    return flow["properties"]["definition"]["actions"]


def paging_block(flow):
    return actions(flow)["Get_all_pages"]["actions"]


@pytest.fixture
def graph():
    """A fresh local Graph stand-in per test (127.0.0.1, random port)."""
    with MockGraph(sample("directory.json")) as g:
        yield g


class Harness:
    """Runs the flow against the mock: environment variables point at it, sleeps are recorded, mail is captured."""

    def __init__(self, graph):
        self.graph = graph
        self.waits: list[float] = []
        self.mail: list[dict] = []

    def params(self, page_size="2"):
        return {"Graph base URL (cts_GraphBaseUrl)": self.graph.url,
                "Entra authority (cts_EntraAuthority)": self.graph.url,
                "Entra tenant ID (cts_EntraTenantId)": self.graph.state.tenant,
                "Graph client ID (cts_GraphClientId)": self.graph.state.client_id,
                "Graph page size (cts_GraphPageSize)": page_size}

    def mocks(self, secret=None):
        def send(inputs):
            self.mail.append(inputs["parameters"])
            return OK
        secret = self.graph.state.client_secret if secret is None else secret
        return {"Get_client_secret": {"status": "Succeeded", "body": {"EnvironmentVariableSecretValue": secret}},
                "Send_report": send, "Notify_failure": send}

    def run(self, flow, secret=None, page_size="2"):
        return run_flow(flow, None, self.mocks(secret), parameters=self.params(page_size), sleep=self.waits.append)


@pytest.fixture
def harness(graph):
    return Harness(graph)


def page_calls(result, name="Get_users_page"):
    """Every recorded run of an action inside the Until loop, in order."""
    return [r for n, r in result.history if n == name and r.status != "Skipped"]
