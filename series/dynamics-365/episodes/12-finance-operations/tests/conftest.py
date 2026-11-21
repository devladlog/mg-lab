"""Test helpers: a recording stub for requests.Session.request. Only for the automated tests; demo.md runs everything
against the real Business Central container and the real Dataverse environment."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bckit.bc import BcApi  # noqa: E402
from bckit.dataverse import DataverseApi  # noqa: E402

BC_BASE = "http://mglab-bc:7048/BC"
ROOT_URL = BC_BASE + "/api/v2.0"
DV_ENV = "https://contoso-lab.crm4.dynamics.com"
COMPANY_ID = "00000000-0000-0000-0000-0000000000a1"
COMPANY_ID2 = "00000000-0000-0000-0000-0000000000a2"


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

    def request(self, method, url, json=None, headers=None, timeout=None, **_):
        req = {"method": method, "url": unquote(url), "headers": headers or {}, "json": json}
        self.requests.append(req)
        for rx, resp in reversed(self.routes):
            if rx.search(method + " " + req["url"]):
                if isinstance(resp, Exception):
                    raise resp
                return resp(req) if callable(resp) else resp
        return FakeResponse(404, {"error": {"code": "BadRequest_NotFound", "message": f"stub: no route for {req['url']}"}})


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def bc(stub):
    return BcApi(BC_BASE, "admin", "not-a-real-password", session=stub, sleep=lambda s: None)


@pytest.fixture
def dv(stub):
    return DataverseApi(DV_ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


@pytest.fixture
def cfg():
    return json.loads((ROOT / "bc.json").read_text())


def sample(name):
    return json.loads((ROOT / "sample" / name).read_text())


def two_companies(stub):
    stub.on(r"GET .*/api/v2\.0/companies$", FakeResponse(200, {"value": [
        {"id": COMPANY_ID, "name": "CRONUS USA, Inc.", "displayName": "CRONUS USA, Inc."},
        {"id": COMPANY_ID2, "name": "Contoso Test Co", "displayName": "Contoso Test Co"}]}))
    return stub
