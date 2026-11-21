"""Test helpers.

- StubSession: a recording stand-in for requests.Session.request with canned routes (as in episodes 3 and 4).
- Registry: a tiny in-memory answer machine for the registration tables, so `deploy` can be run twice and the
  second run must find what the first one created. It understands only the queries apikit sends
  (`$filter` with `eq` joined by `and`, `_x_value` lookups, `$expand` of the custom API properties).
  It proves what we SEND and that deploy is idempotent; it proves nothing about the real service: that's what the
  lab-tenant run in demo.md is for.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apikit import cli  # noqa: E402
from apikit.webapi import WebApi  # noqa: E402

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


# lookup filter name -> the @odata.bind key apikit uses when creating the row
LOOKUPS = {"_pluginassemblyid_value": "pluginassemblyid@odata.bind",
           "_eventhandler_value": "eventhandler_plugintype@odata.bind",
           "_sdkmessagefilterid_value": "sdkmessagefilterid@odata.bind",
           "_sdkmessageprocessingstepid_value": "sdkmessageprocessingstepid@odata.bind",
           "_plugintypeid_value": "PluginTypeId@odata.bind"}
ID_FIELD = {"pluginassemblies": "pluginassemblyid", "plugintypes": "plugintypeid", "customapis": "customapiid",
            "customapiresponseproperties": "customapiresponsepropertyid",
            "sdkmessageprocessingsteps": "sdkmessageprocessingstepid",
            "sdkmessageprocessingstepimages": "sdkmessageprocessingstepimageid",
            "sdkmessages": "sdkmessageid", "sdkmessagefilters": "sdkmessagefilterid"}
MSG_CREATE, MSG_UPDATE = "00000000-0000-0000-0000-00000000c001", "00000000-0000-0000-0000-00000000c002"
FLT_CREATE, FLT_UPDATE = "00000000-0000-0000-0000-00000000f001", "00000000-0000-0000-0000-00000000f002"


def bound_id(value):
    return value.rsplit("(", 1)[1].rstrip(")") if isinstance(value, str) and "(" in value else value


class Registry(StubSession):
    def __init__(self):
        super().__init__()
        self.rows = {k: [] for k in ID_FIELD}
        self.columns = set()
        self.n = 0
        self.rows["sdkmessages"] = [{"sdkmessageid": MSG_CREATE, "name": "Create"},
                                    {"sdkmessageid": MSG_UPDATE, "name": "Update"}]
        self.rows["sdkmessagefilters"] = [
            {"sdkmessagefilterid": FLT_CREATE, "primaryobjecttypecode": "mgl_projectrequest", "_sdkmessageid_value": MSG_CREATE},
            {"sdkmessagefilterid": FLT_UPDATE, "primaryobjecttypecode": "mgl_projectrequest", "_sdkmessageid_value": MSG_UPDATE}]

    def new_id(self):
        self.n += 1
        return f"00000000-0000-0000-0000-{self.n:012x}"

    @staticmethod
    def _matches(row, conditions):
        for field, val in conditions:
            have = row.get(field)
            if have is None and field in LOOKUPS:
                have = bound_id(row.get(LOOKUPS[field]))
            if str(have) != val:
                return False
        return True

    def fallback(self, req):
        m, url = req["method"], req["url"]
        attr = re.match(r"^EntityDefinitions\(LogicalName='(\w+)'\)/Attributes(?:\(LogicalName='(\w+)'\))?", url)
        if attr:
            if m == "GET":
                return FakeResponse(200, {"LogicalName": attr.group(2)}) if attr.group(2) in self.columns else not_found()
            if m == "POST":
                self.columns.add(req["json"]["SchemaName"].lower())
                return FakeResponse(204, None, {"OData-EntityId": f"{API}{url}({self.new_id()})"})
        es = re.match(r"^(\w+)(?:\(([0-9a-f-]{36})\))?", url)
        if not es or es.group(1) not in self.rows:
            return not_found(f"stub: no route for {m} {url}")
        name, rid = es.group(1), es.group(2)
        table, idf = self.rows[name], ID_FIELD[name]
        if m == "POST":
            row = dict(req["json"])
            row[idf] = self.new_id()
            if name == "customapis":
                for p in row.get("CustomAPIResponseProperties", []):
                    p["customapiresponsepropertyid"] = self.new_id()
            table.append(row)
            return FakeResponse(204, None, {"OData-EntityId": f"{API}{name}({row[idf]})"})
        if m == "PATCH":
            row = next(r for r in table if r[idf] == rid)
            row.update(req["json"])
            return FakeResponse(204)
        if m == "DELETE":
            self.rows[name] = [r for r in table if r[idf] != rid]
            return FakeResponse(204)
        flt = re.search(r"\$filter=(.*?)(?:&\$|$)", url)
        conditions = []
        if flt:
            for part in flt.group(1).split(" and "):
                f, _, v = part.partition(" eq ")
                conditions.append((f.strip(), v.strip().strip("'")))
        found = [r for r in table if self._matches(r, conditions)]
        if name == "customapis":
            for r in found:
                extra = [p for p in self.rows["customapiresponseproperties"]
                         if bound_id(p.get("CustomAPIId@odata.bind")) == r["customapiid"]]
                r.setdefault("CustomAPIRequestParameters", [])
                r["CustomAPIResponseProperties"] = [p for p in r["CustomAPIResponseProperties"]
                                                    if "CustomAPIId@odata.bind" not in p] + extra
                r["_plugintypeid_value"] = bound_id(r.get("PluginTypeId@odata.bind"))
        return FakeResponse(200, {"value": [dict(r) for r in found]})


@pytest.fixture
def cfg():
    return cli.load_config()


@pytest.fixture
def stub():
    return StubSession()


@pytest.fixture
def api(stub):
    return WebApi(ENV, lambda: "test-token", session=stub, sleep=lambda s: None)


@pytest.fixture
def registry():
    return Registry()


@pytest.fixture
def reg_api(registry, cfg):
    return WebApi(ENV, lambda: "test-token", solution=cfg["solution"], session=registry, sleep=lambda s: None)


def value(*rows):
    return FakeResponse(200, {"value": list(rows)})
