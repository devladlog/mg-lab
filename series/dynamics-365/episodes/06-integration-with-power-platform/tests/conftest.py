"""Test helpers: a recording stub for requests.Session.request (as in episodes 3-5) and the sample flows.

The stub checks what flowkit SENDS and answers like the Learn examples. The sample clientdata is hand-written (see
README): it proves the linter's logic, not the exact keys the designer exports. demo.md replaces it with a real pull.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flowkit import cli, definition  # noqa: E402
from flowkit.webapi import WebApi  # noqa: E402

ENV = "https://contoso-dev.crm4.dynamics.com"
API = ENV + "/api/data/v9.2/"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def not_found(msg="stub: not found"):
    return FakeResponse(404, {"error": {"code": "0x80040217", "message": msg}})


class StubSession:
    """routes: (METHOD, regex on the decoded relative URL, response or callable(req) -> response). Later wins."""

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
        return self.fallback(req)

    def fallback(self, req):
        return not_found(f"stub: no route for {req['method']} {req['url']}")

    def sent(self, method, pattern=""):
        return [r for r in self.requests if r["method"] == method and re.search(pattern, r["url"])]



SAMPLE = ROOT / "sample" / "notify-high-risk.clientdata.json"
BAD = ROOT / "tests" / "fixtures" / "bad-flow.clientdata.json"
WF = "00000000-0000-0000-0000-00000000f10e"


@pytest.fixture
def cfg():
    return cli.load_config()


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def api(stub, cfg):
    return WebApi(ENV, lambda: "test-token", solution=cfg["solution"], session=stub, sleep=lambda s: None)


@pytest.fixture
def good():
    return json.loads(SAMPLE.read_text())


@pytest.fixture
def bad():
    return json.loads(BAD.read_text())


def flow(data):
    return definition.Flow(definition.load_clientdata(data))


def value(*rows):
    return FakeResponse(200, {"value": list(rows)})


def created(entity_set, guid="00000000-0000-0000-0000-0000000000ff"):
    return FakeResponse(204, None, {"OData-EntityId": f"{API}{entity_set}({guid})"})
