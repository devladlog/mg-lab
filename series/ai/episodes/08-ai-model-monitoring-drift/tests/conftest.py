"""Test doubles. Nothing here calls Azure:
- a local HTTP server imitates the Azure OpenAI v1 chat completions endpoint (keyword rules, NOT the model);
- a requests adapter inside the real azure-core RequestsTransport answers Log Analytics queries with canned tables.
The real SDKs (openai, azure-monitor-query, OpenTelemetry) run against them."""
import io
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests
from requests.adapters import BaseAdapter
from urllib3.response import HTTPResponse
from azure.monitor.query import LogsQueryClient as _RealLogsQueryClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RULES = [("hybrid", "benefits"), ("híbrido", "benefits"), ("teletrabalho", "benefits"), ("payslip", "payroll"),
         ("recibo", "payroll"), ("salary", "payroll"), ("leave", "leave"), ("férias", "leave"), ("holiday", "leave"),
         ("mentoring", "career"), ("job opening", "career"), ("laptop", "equipment"), ("monitor", "equipment"), ("portátil", "equipment"), ("promotion", "career"),
         ("gym", "benefits"), ("jokes", "conduct"), ("colleague", "conduct")]


class AoaiStub:
    def __init__(self):
        self.requests = []
        self.model = "gpt-5-mini-2025-08-07"
        self.fail_on: str | None = None
        self.override: dict[str, str] = {}      # substring -> category (simulates a model behaving differently)
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                stub.requests.append({"path": urlparse(self.path).path, "body": body,
                                      "auth": self.headers.get("authorization", "")})
                user = body["messages"][-1]["content"]
                if stub.fail_on and stub.fail_on in user:
                    status, payload = 500, {"error": {"code": "InternalServerError", "message": "boom"}}
                else:
                    status, payload = 200, stub.completion(user)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def completion(self, user):
        low = user.lower()
        cat = next((c for k, c in self.override.items() if k in low), None) or \
            next((c for k, c in RULES if k in low), "other")
        content = json.dumps({"category": cat, "urgency": "high" if cat == "conduct" else "normal",
                              "needs_human": cat in ("conduct", "payroll")})
        return {"id": "c1", "object": "chat.completion", "created": 0, "model": self.model,
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}}


@pytest.fixture
def aoai_stub():
    s = AoaiStub()
    yield s
    s.server.shutdown()


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


@pytest.fixture
def client(aoai_stub):
    from hrmon.triage import make_openai_client
    cred = FakeCredential()
    c = make_openai_client(aoai_stub.url, cred)
    c.test_credential = cred
    return c


class FakeLogAnalytics(BaseAdapter):
    """Answers POST /v1/workspaces/{id}/query with a table built from local records (same shape as the REST API)."""

    def __init__(self, records):
        super().__init__()
        self.records = records
        self.requests = []
        self.partial = False

    def send(self, request, **kwargs):
        body = json.loads(request.body or b"{}")
        self.requests.append({"url": request.url, "headers": dict(request.headers), "body": body})
        cols = ["TimeGenerated", "Message", "window", "lang", "length", "category", "urgency", "needs_human",
                "model", "golden_accuracy"]
        wanted = re.search(r"where window in \((.*?)\)", body["query"]).group(1).replace('"', "").split(", ")
        rows = []
        for r in self.records:
            if r["message"] in ("triage", "quality") and r["hr_window"] in wanted:
                rows.append(["2026-12-01T10:00:00Z", r["message"], r["hr_window"]]
                            + [str(r.get(f"hr_{c}", "")) if f"hr_{c}" in r else "" for c in cols[3:9]]
                            + [r.get("hr_golden_accuracy")])
        payload = {"tables": [{"name": "PrimaryResult",
                               "columns": [{"name": c, "type": "real" if c == "golden_accuracy" else "string"}
                                           for c in cols], "rows": rows}]}
        if self.partial:
            payload["error"] = {"code": "PartialError", "message": "query hit a limit"}
        data = json.dumps(payload).encode()
        r = requests.Response()
        r.status_code = 200
        r.raw = HTTPResponse(body=io.BytesIO(data), status=200, preload_content=False,
                             headers={"content-type": "application/json", "content-length": str(len(data))})
        r._content = data
        r.headers.update({"content-type": "application/json", "content-length": str(len(data))})
        r.url, r.request = request.url, request
        return r

    def close(self):
        pass


def logs_client(adapter):
    from azure.core.pipeline.transport import RequestsTransport
    session = requests.Session()
    session.mount("https://", adapter)
    cred = FakeCredential()
    c = _RealLogsQueryClient(cred, transport=RequestsTransport(session=session, session_owner=False))
    c.test_credential = cred
    return c
