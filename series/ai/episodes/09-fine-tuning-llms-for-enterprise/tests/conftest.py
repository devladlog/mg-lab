"""Test doubles. Nothing here calls Azure. A local HTTP server imitates, with canned answers:
  - the Azure OpenAI v1 endpoint (files, fine_tuning/jobs, events, result file, chat completions);
  - the ARM deployments endpoint (PUT / GET / DELETE).
The REAL openai SDK and requests talk to it. The 'models' are lookup tables over the labelled data, NOT language
models: tests prove our plumbing, metrics and gates, not model quality."""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fttriage import dataset  # noqa: E402


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


RESULTS_CSV = ("step,train_loss,train_mean_token_accuracy,valid_loss,valid_mean_token_accuracy,full_valid_loss,"
               "full_valid_mean_token_accuracy\n1,1.20,0.60,,,,\n10,0.40,0.85,0.55,0.80,0.52,0.82\n"
               "20,0.10,0.97,0.50,0.84,0.48,0.85\n")


class Stub:
    def __init__(self):
        self.requests: list[dict] = []
        self.job_states = ["queued", "running", "succeeded"]
        self.job_polls = 0
        self.fine_tuned_model = "gpt-4.1-mini-2025-04-14.ft-" + "a" * 32 + "-hr-triage"
        self.results_csv = RESULTS_CSV
        self.behaviours: dict[str, callable] = {}     # deployment name -> fn(user_text, system) -> raw answer text
        self.chat_fail_on: str | None = None
        self.arm_states = ["Creating", "Succeeded"]
        self.arm_polls = 0
        self.arm_put_status = 201
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, payload, ctype="application/json"):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                return self.rfile.read(int(self.headers.get("content-length", 0)))

            def _rec(self, body=b""):
                u = urlparse(self.path)
                stub.requests.append({"method": self.command, "path": u.path, "query": u.query, "body": body,
                                      "auth": self.headers.get("authorization", "")})
                return u.path

            def do_POST(self):
                body = self._body()
                path = self._rec(body)
                if path.endswith("/openai/v1/files"):
                    return self._send(200, {"id": f"file-{len([r for r in stub.requests if r['path'].endswith('/files')])}",
                                            "object": "file", "status": "pending", "purpose": "fine-tune",
                                            "bytes": len(body), "created_at": 0, "filename": "x.jsonl"})
                if path.endswith("/fine_tuning/jobs"):
                    return self._send(200, {"id": "ftjob-1", "object": "fine_tuning.job", "status": "queued",
                                            "model": json.loads(body)["model"], "created_at": 0, "fine_tuned_model": None})
                if path.endswith("/chat/completions"):
                    d = json.loads(body)
                    system, user = d["messages"][0]["content"], d["messages"][-1]["content"]
                    if stub.chat_fail_on and stub.chat_fail_on in user:
                        return self._send(500, {"error": {"code": "InternalServerError", "message": "boom"}})
                    raw = stub.behaviours[d["model"]](user, system)
                    return self._send(200, {"id": "c1", "object": "chat.completion", "created": 0, "model": d["model"],
                                            "choices": [{"index": 0, "finish_reason": "stop",
                                                         "message": {"role": "assistant", "content": raw}}],
                                            "usage": {"prompt_tokens": (len(system) + len(user)) // 4,
                                                      "completion_tokens": 20, "total_tokens": 0}})
                self._send(404, {"error": "nope"})

            def do_GET(self):
                path = self._rec()
                if re.search(r"/openai/v1/files/[^/]+/content$", path):
                    return self._send(200, stub.results_csv.encode(), "text/csv")
                if re.search(r"/openai/v1/files/[^/]+$", path):
                    return self._send(200, {"id": path.rsplit("/", 1)[1], "object": "file", "status": "processed",
                                            "purpose": "fine-tune", "bytes": 1, "created_at": 0, "filename": "x.jsonl"})
                if path.endswith("/events"):
                    return self._send(200, {"object": "list", "has_more": False, "data": [
                        {"id": "ev2", "object": "fine_tuning.job.event", "created_at": 2, "level": "info",
                         "message": "Training started"},
                        {"id": "ev1", "object": "fine_tuning.job.event", "created_at": 1, "level": "info",
                         "message": "Job enqueued"}]})
                if path.endswith("/fine_tuning/jobs/ftjob-1"):
                    state = stub.job_states[min(stub.job_polls, len(stub.job_states) - 1)]
                    stub.job_polls += 1
                    d = {"id": "ftjob-1", "object": "fine_tuning.job", "status": state, "model": "gpt-4.1-mini-2025-04-14",
                         "created_at": 0, "fine_tuned_model": None, "result_files": []}
                    if state == "succeeded":
                        d.update(fine_tuned_model=stub.fine_tuned_model, result_files=["file-results"])
                    if state == "failed":
                        d["error"] = {"code": "invalid_training_file", "message": "line 3 is not valid"}
                    return self._send(200, d)
                if "/Microsoft.CognitiveServices/accounts/" in path and "/deployments/" in path:
                    state = stub.arm_states[min(stub.arm_polls, len(stub.arm_states) - 1)]
                    stub.arm_polls += 1
                    return self._send(200, {"name": path.rsplit("/", 1)[1], "properties": {"provisioningState": state}})
                self._send(404, {"error": "nope"})

            def do_PUT(self):
                body = self._body()
                self._rec(body)
                self._send(stub.arm_put_status, {"properties": {"provisioningState": "Creating"}})

            def do_DELETE(self):
                path = self._rec()
                if "/openai/v1/files/" in path:
                    return self._send(200, {"id": path.rsplit("/", 1)[1], "object": "file", "deleted": True})
                self._send(200, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def last(self, method, suffix):
        return [r for r in self.requests if r["method"] == method and r["path"].endswith(suffix)][-1]


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.server.shutdown()


@pytest.fixture
def client(stub):
    from fttriage.jobs import make_client
    cred = FakeCredential()
    c = make_client(stub.url, cred)
    c.test_credential = cred
    return c


@pytest.fixture(scope="session")
def data():
    ex = dataset.load_labelled(ROOT / "data" / "labelled.jsonl")
    golden = dataset.load_golden(ROOT / "data" / "golden_ep08.jsonl")
    return ex, golden, dataset.split(ex)


def oracle(items, wrong_ids=(), malformed_ids=()):
    """A fake model that knows the answers; it gets `wrong_ids` wrong and returns prose for `malformed_ids`."""
    by_text = {e.text: e for e in items}

    def answer(user, system):
        e = by_text[user]
        if e.id in malformed_ids:
            return "Sure! This looks like a payroll question."
        lab = e.label or None
        cat = "other" if e.id in wrong_ids and e.category != "other" else e.category
        if lab is None:
            return json.dumps({"category": cat, "urgency": "normal", "needs_human": False})
        return json.dumps({"category": cat, "urgency": lab.urgency, "needs_human": lab.needs_human})
    return answer
