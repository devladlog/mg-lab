import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ATTACK_MARKERS = ("Ignore all previous", "developer mode", "DAN")
DOC_ATTACK_MARKERS = ("NOTE TO THE ASSISTANT", "Disregard all prior")


class LocalAzureStub:
    """One local HTTP server that imitates the three endpoints the gate uses:

    - POST /contentsafety/text:analyze       (Content Safety, harm categories)
    - POST /contentsafety/text:shieldPrompt  (Content Safety, Prompt Shields)
    - POST /openai/v1/chat/completions       (Azure OpenAI; 400 content_filter for attacks, triage JSON otherwise)

    Its verdicts come from fixed keyword rules so tests are deterministic. They are NOT the service's behaviour;
    the real numbers come from the recorded run against the lab resources.
    """

    def __init__(self):
        self.requests = []
        self.severity_overrides: dict[str, dict] = {}   # substring -> severities
        self.triage_bias: dict[str, dict] = {}          # name substring -> fields to override in triage output
        self.triage_cycle: list[dict] | None = None     # scripted triage outputs (noise tests)
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
                url = urlparse(self.path)
                body = json.loads(raw or b"{}")
                stub.requests.append({"path": url.path, "query": parse_qs(url.query),
                                      "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                status, payload = stub.route(url.path, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    # --- routing ---------------------------------------------------------------------------------------------------
    def route(self, path, body):
        if path == "/contentsafety/text:analyze":
            return 200, self.analyze(body["text"])
        if path == "/contentsafety/text:shieldPrompt":
            return 200, {
                "userPromptAnalysis": {"attackDetected": any(m in body["userPrompt"] for m in ATTACK_MARKERS)},
                "documentsAnalysis": [{"attackDetected": any(m in d for m in DOC_ATTACK_MARKERS)}
                                      for d in body["documents"]],
            }
        if path == "/openai/v1/chat/completions":
            return self.chat(body)
        return 404, {"error": {"code": "NotFound"}}

    def analyze(self, text):
        sev = {"Hate": 0, "Sexual": 0, "Violence": 0, "SelfHarm": 0}
        if "better off without me" in text:
            sev["SelfHarm"] = 4
        if "killing" in text:
            sev["Violence"] = 2
        if "useless" in text:
            sev["Hate"] = 2
        for marker, override in self.severity_overrides.items():
            if marker in text:
                sev.update(override)
        return {"blocklistsMatch": [], "categoriesAnalysis": [{"category": k, "severity": v} for k, v in sev.items()]}

    def chat(self, body):
        user = body["messages"][-1]["content"]
        if "response_format" not in body and any(m in user for m in ATTACK_MARKERS):
            return 400, {"error": {
                "message": "The response was filtered due to the prompt triggering content management policy.",
                "type": None, "param": "prompt", "code": "content_filter", "status": 400,
                "innererror": {"code": "ResponsibleAIPolicyViolation", "content_filter_result": {
                    "hate": {"filtered": False, "severity": "safe"}, "jailbreak": {"filtered": True, "detected": True},
                    "self_harm": {"filtered": False, "severity": "safe"}, "sexual": {"filtered": False, "severity": "safe"},
                    "violence": {"filtered": False, "severity": "safe"}}}}}
        if "response_format" in body:
            content = json.dumps(self.triage(user))
        else:
            content = "Here is what the HR policy says."
        return 200, {"id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "gpt-5-mini",
                     "choices": [{"index": 0, "finish_reason": "stop",
                                  "message": {"role": "assistant", "content": content}}],
                     "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}}

    def triage(self, text):
        if self.triage_cycle:
            return self.triage_cycle.pop(0)
        rules = [("payslip", "payroll", "high", True), ("complaint", "conduct", "high", True),
                 ("promotion", "career", "high", True), ("leave", "leave", "normal", False),
                 ("charger", "equipment", "low", False), ("gym", "benefits", "low", False)]
        cat, urg, human = next(((c, u, h) for kw, c, u, h in rules if kw in text), ("other", "normal", False))
        out = {"category": cat, "urgency": urg, "needs_human": human}
        for name, override in self.triage_bias.items():
            if name in text:
                out.update(override)
        return out

    def of(self, path):
        return [r for r in self.requests if r["path"] == path]


@pytest.fixture
def stub():
    s = LocalAzureStub()
    yield s
    s.server.shutdown()


@pytest.fixture
def safety(stub):
    # The SDK refuses bearer tokens over plain HTTP, so the local tests use a fake key credential;
    # make_safety_client() uses DefaultAzureCredential against the real (HTTPS) endpoint.
    from azure.core.credentials import AzureKeyCredential

    from raigate.safety import make_safety_client

    return make_safety_client(stub.url, AzureKeyCredential("fake-key"))


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
def credential():
    return FakeCredential()


@pytest.fixture
def aoai(stub, credential):
    from raigate.model import make_openai_client

    return make_openai_client(stub.url, credential)
