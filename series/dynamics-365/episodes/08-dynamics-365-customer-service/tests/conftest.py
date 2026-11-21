"""Test helpers: a recording stub for requests.Session.request (as in episodes 3-7).
The stub is only for the automated tests; demo.md runs everything against the real Sales trial environment."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from casekit.webapi import WebApi  # noqa: E402

ENV = "https://contoso-service.crm4.dynamics.com"
API = ENV + "/api/data/v9.2/"
SAMPLE = ROOT / "sample" / "open-cases.json"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def not_found(msg="stub: not found"):
    return FakeResponse(404, {"error": {"code": "0x80040217", "message": msg}})


class StubSession:
    """routes: (METHOD, regex on the decoded relative URL, response or callable(req)). Later routes win."""

    def __init__(self):
        self.routes, self.requests = [], []

    def on(self, method, pattern, response):
        self.routes.append((method, re.compile(pattern), response))
        return self

    def request(self, method, url, json=None, headers=None, **_):
        rel = unquote(url[len(API):]) if url.startswith(API) else unquote(url)
        req = {"method": method, "url": rel, "json": json, "headers": headers or {}}
        self.requests.append(req)
        for m, rx, resp in reversed(self.routes):
            if m == method and rx.search(rel):
                return resp(req) if callable(resp) else resp
        return not_found(f"stub: no route for {method} {rel}")

    def sent(self, method, pattern=""):
        return [r for r in self.requests if r["method"] == method and re.search(pattern, r["url"])]


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def api(stub):
    return WebApi(ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


@pytest.fixture
def rows():
    return json.loads(SAMPLE.read_text())["value"]
