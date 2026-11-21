"""Test helpers: a recording stub for requests.Session.request, answering with canned Web API responses.

The stub only checks what custkit SENDS (method, URL, headers, body) and returns responses shaped like the
Learn examples (204 + OData-EntityId on create, {"value": [...]} on queries). It proves nothing about the real
service: that's what the lab-tenant run in demo.md is for.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from custkit import cli  # noqa: E402
from custkit.webapi import WebApi  # noqa: E402

ENV = "https://contoso-dev.crm4.dynamics.com"
API = ENV + "/api/data/v9.2/"
FIXTURE_FORM = (ROOT / "tests" / "fixtures" / "main_form.xml").read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class StubSession:
    """routes: list of (METHOD, regex on the decoded relative URL, response or callable(req) -> response)."""

    def __init__(self):
        self.routes, self.requests = [], []

    def on(self, method, pattern, response):
        self.routes.append((method, re.compile(pattern), response))
        return self

    def request(self, method, url, json=None, headers=None, **_):
        rel = unquote(url[len(API):]) if url.startswith(API) else unquote(url)
        req = {"method": method, "url": rel, "json": json, "headers": headers or {}}
        self.requests.append(req)
        for m, rx, resp in reversed(self.routes):       # later routes win
            if m == method and rx.search(rel):
                return resp(req) if callable(resp) else resp
        return FakeResponse(404, {"error": {"code": "0x80040217", "message": f"stub: no route for {method} {rel}"}})

    def sent(self, method, pattern=""):
        return [r for r in self.requests if r["method"] == method and re.search(pattern, r["url"])]


@pytest.fixture
def cfg():
    return cli.load_config()


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def api(stub, cfg):
    return WebApi(ENV, lambda: "test-token", solution=cfg["solution"], session=stub, sleep=lambda s: None)


def created(entity_set, guid="00000000-0000-0000-0000-0000000000ff"):
    return FakeResponse(204, None, {"OData-EntityId": f"{API}{entity_set}({guid})"})


def value(*rows):
    return FakeResponse(200, {"value": list(rows)})
