import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class ResponsesStub:
    """Local HTTP server that imitates POST {endpoint}/openai/v1/responses.

    Each request is recorded; each reply pops the next scripted list of output items. The real Agent Framework
    client (and the real openai SDK under it) talks to it, so the tests see the exact JSON the agent sends.
    """

    def __init__(self):
        self.requests: list[dict] = []
        self.script: list[list[dict]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
                stub.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": json.loads(raw or b"{}")})
                if not stub.script:
                    self._send(500, {"error": {"message": "stub script exhausted", "type": "server_error"}})
                    return
                n = len(stub.requests)
                self._send(200, {
                    "id": f"resp_{n}", "object": "response", "created_at": 0, "status": "completed",
                    "model": "chat", "output": stub.script.pop(0), "parallel_tool_calls": False,
                    "tool_choice": "auto", "tools": [],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                              "input_tokens_details": {"cached_tokens": 0},
                              "output_tokens_details": {"reasoning_tokens": 0}},
                })

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bodies(self):
        return [r["body"] for r in self.requests]


_ids = iter(range(1, 10_000))


def call(name: str, **arguments) -> dict:
    """A function_call output item, as the Responses API returns it."""
    n = next(_ids)
    return {"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": name,
            "arguments": json.dumps(arguments), "status": "completed"}


def say(text: str) -> dict:
    n = next(_ids)
    return {"type": "message", "id": f"msg_{n}", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


class FakeCredential:
    """Stands in for DefaultAzureCredential; records the scopes asked for."""

    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken

        self.scopes.extend(scopes)
        return AccessToken("fake-entra-token", 4_102_444_800)


@pytest.fixture
def stub(monkeypatch):
    # The generic OpenAI client stays on OpenAI if OPENAI_API_KEY is set; make sure the test is on the Azure path.
    for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = ResponsesStub()
    yield s
    s.server.shutdown()


@pytest.fixture
def credential():
    return FakeCredential()


@pytest.fixture
def client(stub, credential):
    from apagent.agent import make_client

    return make_client(stub.url, "chat", credential=credential)
