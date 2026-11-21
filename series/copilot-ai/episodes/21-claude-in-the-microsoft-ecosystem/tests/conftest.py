import json
import pathlib

import httpx2 as httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def message(content, stop_reason="end_turn", inp=10, out=5):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-test",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": inp, "output_tokens": out},
    }


def text(t):
    return {"type": "text", "text": t}


def tool_use(id_, name, inp):
    return {"type": "tool_use", "id": id_, "name": name, "input": inp}


class Script:
    """A scripted Foundry endpoint: replies in order, records every request (url, headers, json body)."""

    def __init__(self, replies):
        self.replies = list(replies)  # each: (status, json) 
        self.seen = []

    def __call__(self, request):
        self.seen.append((str(request.url), dict(request.headers), json.loads(request.content)))
        status, body = self.replies.pop(0)
        return httpx.Response(status, json=body)

    def client(self, **kw):
        from claude_ms.client import build_client

        http = httpx.Client(transport=httpx.MockTransport(self))
        kw.setdefault("token_provider", lambda: "test-token")
        return build_client("contoso-foundry", http_client=http, env={}, **kw)[0]


@pytest.fixture
def vendors():
    from claude_ms.triage import load_vendors

    return load_vendors(str(ROOT / "src" / "samples" / "vendors.json"))
