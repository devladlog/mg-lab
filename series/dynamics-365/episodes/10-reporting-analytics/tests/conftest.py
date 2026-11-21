"""Test helpers: a recording stub for requests.Session.request (as in episodes 3-9).
The stub is only for the automated tests; demo.md runs everything against the real lab environment."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reportkit.webapi import WebApi  # noqa: E402

ENV = "https://contoso-sales.crm4.dynamics.com"
API = ENV + "/api/data/v9.2/"
SAMPLE = ROOT / "sample" / "open-opportunities.json"


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


FMT = "@OData.Community.Display.V1.FormattedValue"


def by_category(rows):
    """Independent computation of the expected aggregate, in the shape the Web API returns it."""
    groups = {}
    for r in rows:
        g = groups.setdefault(r["msdyn_forecastcategory"], {"n": 0, "total": 0.0, "label": r[
            "msdyn_forecastcategory" + FMT]})
        g["n"] += 1
        g["total"] += r["estimatedvalue"] or 0
    return groups


def fetch_response(rows):
    return {"value": [{"grp": k, "grp" + FMT: v["label"], "total": v["total"], "n": v["n"]}
                      for k, v in sorted(by_category(rows).items())]}


def apply_response(rows):
    return {"value": [{"msdyn_forecastcategory": k, "msdyn_forecastcategory" + FMT: v["label"],
                       "total": v["total"], "n": v["n"]} for k, v in sorted(by_category(rows).items())]}


def month_response(rows):
    groups = {}
    for r in rows:
        d = r["estimatedclosedate"]
        key = (int(d[:4]), int(d[5:7])) if d else (None, None)
        g = groups.setdefault(key, {"n": 0, "total": 0.0})
        g["n"] += 1
        g["total"] += r["estimatedvalue"] or 0
    return {"value": [{"yr": k[0], "mo": k[1], "total": v["total"], "n": v["n"]} for k, v in groups.items()]}


@pytest.fixture
def env(stub, rows):
    """A stub environment that answers the three kinds of request from the sample rows."""
    stub.on("GET", r"^opportunities\?\$select=estimatedvalue", FakeResponse(200, {"value": rows}))
    stub.on("GET", r"^opportunities\?fetchXml=.*msdyn_forecastcategory", FakeResponse(200, fetch_response(rows)))
    stub.on("GET", r"^opportunities\?fetchXml=.*dategrouping", FakeResponse(200, month_response(rows)))
    stub.on("GET", r"^opportunities\?\$apply=", FakeResponse(200, apply_response(rows)))
    return stub
