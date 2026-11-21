"""Test helpers: a recording stub for requests.Session.request, answering with canned Web API responses.

The stub only checks what bpfkit SENDS (method, URL, headers, body) and returns responses shaped like the
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

from bpfkit import cli  # noqa: E402
from bpfkit.webapi import WebApi  # noqa: E402

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
    return WebApi(ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


def created(entity_set, guid="00000000-0000-0000-0000-0000000000ff"):
    return FakeResponse(204, None, {"OData-EntityId": f"{API}{entity_set}({guid})"})


def value(*rows):
    return FakeResponse(200, {"value": list(rows)})


# ---- a fictional "Project Approval" BPF, answered the way the Learn examples show ----
WF = "00000000-0000-0000-0000-0000000000f1"
SUBMIT, FINANCE, APPROVE, CLOSE = ("00000000-0000-0000-0000-0000000005a1", "00000000-0000-0000-0000-0000000005a2",
                                   "00000000-0000-0000-0000-0000000005a3", "00000000-0000-0000-0000-0000000005a4")
REC = "00000000-0000-0000-0000-00000000a004"      # PR-0004
INST = "00000000-0000-0000-0000-00000000b004"


def stage(sid, name):
    return {"processstageid": sid, "stagename": name, "primaryentitytypecode": "mgl_projectrequest"}


def bpf_environment(stub, *, statecode=1):
    stub.on("GET", r"^workflows\?", value({"workflowid": WF, "name": "Project Approval", "uniquename": "mgl_projectapproval",
                                          "primaryentity": "mgl_projectrequest", "statecode": statecode}))
    stub.on("GET", r"^EntityDefinitions\(LogicalName='mgl_projectapproval'\)\?",
            FakeResponse(200, {"EntitySetName": "mgl_projectapprovals", "IsBPFEntity": True}))
    stub.on("GET", r"^EntityDefinitions\(LogicalName='mgl_projectapproval'\)/ManyToOneRelationships", value(
        {"ReferencedEntity": "processstage", "ReferencingAttribute": "activestageid",
         "ReferencingEntityNavigationPropertyName": "activestageid"},
        {"ReferencedEntity": "mgl_projectrequest", "ReferencingAttribute": "bpf_mgl_projectrequestid",
         "ReferencingEntityNavigationPropertyName": "bpf_mgl_projectrequestid"}))
    # unordered on purpose, like Learn's example (S1, S3, S2)
    stub.on("GET", r"^processstages\?", value(stage(SUBMIT, "Submit"), stage(CLOSE, "Close"),
                                             stage(APPROVE, "Approve"), stage(FINANCE, "Finance Review")))
    stub.on("GET", r"^mgl_projectrequests\(mgl_requestcode='PR-0004'\)",
            FakeResponse(200, {"mgl_projectrequestid": REC, "mgl_name": "Warehouse IoT sensors"}))
    return stub


def with_instance(stub, *, stage_id=SUBMIT, traversed=SUBMIT, statecode=0, statuscode=1,
                  path=(SUBMIT, FINANCE, APPROVE, CLOSE)):
    stub.on("GET", r"^mgl_projectapprovals\?.*_bpf_mgl_projectrequestid_value eq", value({
        "businessprocessflowinstanceid": INST, "_activestageid_value": stage_id, "traversedpath": traversed,
        "statecode": statecode, "statuscode": statuscode, "activestagestartedon": "2027-01-05T09:00:00Z",
        "_bpf_mgl_projectrequestid_value": REC}))
    names = {SUBMIT: "Submit", FINANCE: "Finance Review", APPROVE: "Approve", CLOSE: "Close"}
    stub.on("GET", r"^RetrieveActivePath\(", value(*[stage(s, names[s]) for s in path]))
    stub.on("PATCH", r"^mgl_projectapprovals\(", FakeResponse(204))
    return stub
