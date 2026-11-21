"""Test doubles. Nothing here calls Azure. A local HTTP server imitates, with canned answers, three endpoints of the
Azure OpenAI v1 API: chat completions (vision), audio transcriptions, and audio speech. The REAL openai SDK talks to it.
The 'models' are lookup tables, NOT vision or speech models, and the token counts are made-up numbers: these tests
prove our plumbing, limits, guards and gates, not model quality or real image pricing."""
import email
import email.policy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mmticket import guard, samples  # noqa: E402,F401
from mmticket.images import prepare_image  # noqa: E402


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


def default_ticket(**over):
    t = {"product": "Contoso Connect", "error_code": "CX-4102", "severity": "medium", "queue": "network",
         "needs_human": False, "summary": "VPN gateway does not answer.", "ocr_text": "Connection failed CX-4102"}
    t.update(over)
    return t


class Stub:
    def __init__(self):
        self.requests: list[dict] = []
        self.chat = lambda req: (json.dumps(default_ticket()), "stop")      # req -> (content, finish_reason)
        self.transcripts: dict[str, str] = {}                              # file name -> text
        self.tokens = {"low": 85, "high": 765}                             # made up, per image
        self.chat_fail = False
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, payload, ctype="application/json"):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                ctype = self.headers.get("Content-Type", "")
                rec = {"path": self.path, "auth": self.headers.get("Authorization"), "ctype": ctype}
                stub.requests.append(rec)
                if self.path.endswith("/chat/completions"):
                    req = json.loads(body)
                    rec["json"] = req
                    if stub.chat_fail:
                        return self._send(500, {"error": {"message": "boom"}})
                    content, finish = stub.chat(req)
                    parts = [p for m in req["messages"] if isinstance(m["content"], list) for p in m["content"]]
                    imgs = [p for p in parts if p["type"] == "image_url"]
                    ptok = 40 + sum(stub.tokens[p["image_url"].get("detail", "auto") if p["image_url"].get("detail") in stub.tokens else "high"] for p in imgs)
                    return self._send(200, {"id": "c1", "object": "chat.completion", "created": 1, "model": req["model"],
                                            "choices": [{"index": 0, "finish_reason": finish,
                                                         "message": {"role": "assistant", "content": content}}],
                                            "usage": {"prompt_tokens": ptok, "completion_tokens": 60, "total_tokens": ptok + 60}})
                if self.path.endswith("/audio/transcriptions"):
                    msg = email.message_from_bytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body,
                                                   policy=email.policy.default)
                    fields = {}
                    for part in msg.iter_parts():
                        fields[part.get_param("name", header="content-disposition")] = (
                            part.get_filename(), part.get_payload(decode=True))
                    rec["fields"] = {k: (v[0], v[1] if v[0] else v[1].decode()) for k, v in fields.items()}
                    fname = rec["fields"]["file"][0]
                    return self._send(200, {"text": stub.transcripts.get(fname, " transcript of " + fname + " ")})
                if self.path.endswith("/audio/speech"):
                    rec["json"] = json.loads(body)
                    return self._send(200, b"ID3FAKE-MP3-BYTES", "audio/mpeg")
                self._send(404, {"error": {"message": "no route"}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def last(self, suffix):
        return [r for r in self.requests if r["path"].endswith(suffix)][-1]

    def all(self, suffix):
        return [r for r in self.requests if r["path"].endswith(suffix)]


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
    from mmticket.client import make_client
    return make_client(stub.url, cred)


@pytest.fixture(scope="session")
def cases():
    return {c["id"]: c for c in samples.load_cases()}


@pytest.fixture(scope="session")
def image_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("images")
    samples.write_all(d)
    return d


@pytest.fixture(scope="session")
def by_image(image_dir, cases):
    """data URL (as the client will send it) -> case ids. Two cases share one picture (the conflict case), so the
    fake model also looks at the voice-note text to tell them apart."""
    out = {}
    for cid in cases:
        out.setdefault(prepare_image(image_dir / f"{cid}.png").data_url, []).append(cid)
    return out


def oracle(by_image, cases, wrong_code_at=(), small_text_fails_at_low=False, follow_injection=False, bad_json=(),
           silent=False):
    """A fake vision model that returns the truth, with injectable mistakes. Returns a stub.chat function."""
    def answer(req):
        parts = [p for m in req["messages"] if isinstance(m["content"], list) for p in m["content"]]
        img = [p for p in parts if p["type"] == "image_url"][0]["image_url"]
        user_text = [p for p in parts if p["type"] == "text"][0]["text"]
        cid = next(c for c in by_image[img["url"]]
                   if (cases[c]["voice"] in user_text if cases[c]["voice"] else "No voice note" in user_text))
        if cid in bad_json:
            return "not json at all", "stop"
        t = dict(cases[cid]["truth"])
        t.update({"severity": t["severity"], "summary": "ticket", "ocr_text": " ".join(cases[cid]["lines"] + [cases[cid].get("hidden_text", "")])})
        if silent:                       # a model that never asks for a person: the guards must do it
            t["needs_human"] = False
        if cid in wrong_code_at or (small_text_fails_at_low and cases[cid]["kind"] == "small_text" and img["detail"] == "low"):
            t["error_code"] = "MX-2219"
        if follow_injection and cid == "sync-injection":
            t.update(queue="other", severity="low")
        return json.dumps(t), "stop"
    return answer
