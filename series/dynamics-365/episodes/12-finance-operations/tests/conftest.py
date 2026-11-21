"""Test helpers: a recording stub for requests.Session.request. Only for the automated tests; demo.md runs everything
against the real finance and operations environment."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fokit.dataverse import DataverseApi  # noqa: E402
from fokit.fo import FoApi  # noqa: E402

FO_ENV = "https://contoso-fo.operations.dynamics.com"
DV_ENV = "https://contoso-lab.crm4.dynamics.com"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class StubSession:
    """routes: (regex on the decoded URL, response or callable(req)). Later routes win."""

    def __init__(self):
        self.routes, self.requests = [], []

    def on(self, pattern, response):
        self.routes.append((re.compile(pattern), response))
        return self

    def request(self, method, url, json=None, headers=None, **_):
        req = {"method": method, "url": unquote(url), "headers": headers or {}}
        self.requests.append(req)
        for rx, resp in reversed(self.routes):
            if rx.search(req["url"]):
                return resp(req) if callable(resp) else resp
        return FakeResponse(404, {"error": {"message": f"stub: no route for {req['url']}"}})


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def fo(stub):
    return FoApi(FO_ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


@pytest.fixture
def dv(stub):
    return DataverseApi(DV_ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


@pytest.fixture
def cfg():
    return json.loads((ROOT / "fo.json").read_text())


def sample(name):
    return json.loads((ROOT / "sample" / name).read_text())["value"]
