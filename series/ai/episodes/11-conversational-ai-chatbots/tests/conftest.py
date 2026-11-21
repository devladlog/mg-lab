"""Test doubles. Nothing here calls Azure. A local HTTP server imitates, with scripted answers, the Azure OpenAI v1
chat-completions endpoint, including server-sent-event streaming with a final usage chunk. The REAL openai SDK talks to it.
The 'model' is a function that returns what the test needs and the token counts are made up: these tests prove our
plumbing (memory plan, tools, rollback, handoff rules, gates), NOT how a real model behaves."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken
        self.scopes.extend(scopes)
        return AccessToken("fake-entra-token", 4_102_444_800)

    def get_token_info(self, *scopes, options=None):
        from azure.core.credentials import AccessTokenInfo
        self.scopes.extend(scopes)
        return AccessTokenInfo("fake-entra-token", 4_102_444_800)


def say(text):
    return {"content": text, "finish_reason": "stop"}


def call(name, args, call_id="call_1"):
    return {"content": None, "tool_calls": [{"id": call_id, "name": name,
                                             "arguments": args if isinstance(args, str) else json.dumps(args)}],
            "finish_reason": "tool_calls"}


class Stub:
    def __init__(self):
        self.requests: list[dict] = []
        self.model = lambda req: say("Sure, I can help with that.")      # req -> dict(content, tool_calls, finish_reason) or dict(status=..., body=...)
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                stub.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "json": body})
                if not self.path.endswith("/chat/completions"):
                    return self._json(404, {"error": {"message": "no route"}})
                ans = stub.model(body)
                if "status" in ans:
                    return self._json(ans["status"], ans["body"])
                ptok = sum(len(json.dumps(m)) for m in body["messages"]) // 4 + 50
                ctok = max(1, len(ans.get("content") or "") // 4)
                usage = {"prompt_tokens": ptok, "completion_tokens": ctok, "total_tokens": ptok + ctok}
                if not body.get("stream"):
                    msg = {"role": "assistant", "content": ans.get("content")}
                    return self._json(200, {"id": "c1", "object": "chat.completion", "created": 1, "model": body["model"],
                                            "choices": [{"index": 0, "finish_reason": ans["finish_reason"], "message": msg}],
                                            "usage": usage})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def chunk(choices, usage=None):
                    d = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                         "choices": choices, "usage": usage}
                    self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n")

                chunk([])                                                      # Azure: first chunk has no choices
                if ans.get("content"):
                    for i, w in enumerate(ans["content"].split(" ")):
                        chunk([{"index": 0, "delta": {"role": "assistant", "content": ("" if i == 0 else " ") + w}, "finish_reason": None}])
                for i, tc in enumerate(ans.get("tool_calls") or []):
                    a = tc["arguments"]
                    half = len(a) // 2
                    chunk([{"index": 0, "delta": {"tool_calls": [{"index": i, "id": tc["id"], "type": "function",
                                                                   "function": {"name": tc["name"], "arguments": a[:half]}}]},
                            "finish_reason": None}])
                    chunk([{"index": 0, "delta": {"tool_calls": [{"index": i, "function": {"arguments": a[half:]}}]},
                            "finish_reason": None}])
                chunk([{"index": 0, "delta": {}, "finish_reason": ans["finish_reason"]}])
                if (body.get("stream_options") or {}).get("include_usage"):
                    chunk([], usage)
                self.wfile.write(b"data: [DONE]\n\n")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def chats(self):
        return [r["json"] for r in self.requests if r["path"].endswith("/chat/completions")]


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.server.shutdown()


@pytest.fixture
def cred():
    return FakeCredential()


@pytest.fixture
def client(stub, cred):
    from helpbot.client import make_client
    return make_client(stub.url, cred)


@pytest.fixture
def bot(client):
    from helpbot.bot import Bot
    return Bot(client, "chat")
