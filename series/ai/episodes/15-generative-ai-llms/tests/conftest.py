"""Test doubles. Nothing here calls Azure. A local HTTP server imitates the Azure OpenAI v1 chat completions route with
canned answers (including logprobs and server-sent-event streaming); the REAL openai SDK talks to it. The 'model' is a
lookup table and every number is made up: these tests prove our parsing, arithmetic, gates and request shapes, not how
a real model behaves. Real behaviour is what the demo shows."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmprobe.client import make_client  # noqa: E402


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


def lp(token, logprob, alts):
    return {"token": token, "logprob": logprob, "bytes": None,
            "top_logprobs": [{"token": t, "logprob": l, "bytes": None} for t, l in alts]}


class Stub:
    """handler(req) -> dict(content, finish='stop', logprobs=None, prompt_tokens=50, completion_tokens=20, fingerprint='fp_1')"""

    def __init__(self):
        self.requests: list[dict] = []
        self.handler = lambda req: {"content": "OK"}
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                stub.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "json": body})
                spec = {"finish": "stop", "prompt_tokens": 50, "completion_tokens": 20, "fingerprint": "fp_test", "logprobs": None}
                spec.update(stub.handler(body))
                if body.get("stream"):
                    return self._stream(body, spec)
                msg = {"role": "assistant", "content": spec["content"]}
                choice = {"index": 0, "finish_reason": spec["finish"], "message": msg, "logprobs": spec["logprobs"]}
                data = json.dumps({"id": "c1", "object": "chat.completion", "created": 1, "model": body["model"],
                                   "system_fingerprint": spec["fingerprint"], "choices": [choice],
                                   "usage": {"prompt_tokens": spec["prompt_tokens"], "completion_tokens": spec["completion_tokens"],
                                             "total_tokens": spec["prompt_tokens"] + spec["completion_tokens"]}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _stream(self, body, spec):
                def ev(obj):
                    self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
                base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": body["model"]}
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                # Learn: the first chunk can be filter annotations only, with an empty choices array
                ev({**base, "choices": [], "prompt_filter_results": [{"prompt_index": 0, "content_filter_results": {}}]})
                ev({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
                words = spec["content"].split(" ")
                for i, w in enumerate(words):
                    ev({**base, "choices": [{"index": 0, "delta": {"content": w + (" " if i < len(words) - 1 else "")}, "finish_reason": None}]})
                ev({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": spec["finish"]}]})
                if (body.get("stream_options") or {}).get("include_usage"):
                    ev({**base, "choices": [], "usage": {"prompt_tokens": spec["prompt_tokens"],
                                                         "completion_tokens": spec["completion_tokens"],
                                                         "total_tokens": spec["prompt_tokens"] + spec["completion_tokens"]}})
                self.wfile.write(b"data: [DONE]\n\n")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.close()


@pytest.fixture
def cred():
    return FakeCredential()


@pytest.fixture
def client(stub, cred):
    # make_client appends /openai/v1/ to the endpoint, so the stub serves any path that ends in /chat/completions
    return make_client(stub.url, credential=cred)


@pytest.fixture(scope="session", autouse=True)
def _need_tiktoken_files():
    """tiktoken downloads its vocabulary files on first use. Without network (and without a cache) skip those tests."""
    try:
        import tiktoken
        tiktoken.get_encoding("o200k_base")
        tiktoken.get_encoding("cl100k_base")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"tiktoken vocabulary not available offline: {e}", allow_module_level=False)
