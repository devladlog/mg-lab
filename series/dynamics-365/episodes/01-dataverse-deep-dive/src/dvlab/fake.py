"""An in-memory stand-in for the slice of the Dataverse Web API this episode uses.

It is NOT Dataverse. It exists so the client, the provisioning script and the import can run end to end on a
laptop or in CI with no tenant: it plugs into `requests` as a transport adapter, so the client code is the
same code that talks to the real service. Behaviour it imitates comes from Microsoft Learn:

- POST EntityDefinitions / Attributes / RelationshipDefinitions / Keys return 204 + OData-EntityId
- alternate key index status moves Pending -> InProgress -> Active in the background
- PATCH by key = upsert; If-Match: * = update only (404); If-None-Match: * = create only (412);
  Prefer: return=representation -> 201 on create, 200 on update
- Prefer: odata.maxpagesize + @odata.nextLink paging (values above 5,000 are ignored)
- $batch with change sets (all or nothing) and Prefer: odata.continue-on-error
- 429 Too Many Requests with a Retry-After header (simulated every Nth request when asked)

Error codes/messages are deliberately generic ("fake: ...") - never assert on them as if they were real.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import requests
from requests.adapters import BaseAdapter

from .batch import CRLF

API_PREFIX = "/api/data/v9.2/"


class FakeDataverse(BaseAdapter):
    def __init__(self, *, key_polls_until_active: int = 2, throttle_every: int = 0, retry_after: int = 1):
        super().__init__()
        self.tables: Dict[str, Dict[str, Any]] = {}     # logical name -> {"meta":..., "columns": {...}, "keys": [...]}
        self.rows: Dict[str, Dict[str, Dict[str, Any]]] = {}   # entity set -> id -> row
        self.key_polls_until_active = key_polls_until_active
        self.throttle_every = throttle_every
        self.retry_after = retry_after
        self.request_count = 0
        self.log: List[str] = []

    # ---------- requests adapter API ----------
    def send(self, request: requests.PreparedRequest, **kwargs) -> requests.Response:
        self.request_count += 1
        path = unquote(urlsplit(request.url).path)
        query = urlsplit(request.url).query
        self.log.append(f"{request.method} {path}")
        if not (request.headers.get("Authorization") or "").startswith("Bearer "):
            return self._resp(request, 401, {"error": {"code": "", "message": "fake: missing bearer token"}})
        if self.throttle_every and self.request_count % self.throttle_every == 0:
            return self._resp(request, 429, {"error": {"code": "0x80072322",
                              "message": "Number of requests exceeded the limit of 6000 over time window of 300 seconds."}},
                              {"Retry-After": str(self.retry_after)})
        body = request.body.decode() if isinstance(request.body, bytes) else (request.body or "")
        status, payload, headers = self.handle(request.method, path, unquote(query), dict(request.headers), body)
        return self._resp(request, status, payload, headers)

    def close(self):
        pass

    @staticmethod
    def _resp(req, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> requests.Response:
        r = requests.Response()
        r.status_code = status
        r.request = req
        r.url = req.url
        r.headers.update(headers or {})
        if isinstance(payload, str):
            r._content = payload.encode()
        elif payload is None:
            r._content = b""
        else:
            r._content = json.dumps(payload).encode()
            r.headers.setdefault("Content-Type", "application/json; odata.metadata=minimal")
        r.encoding = "utf-8"
        return r

    # ---------- routing ----------
    def handle(self, method: str, path: str, query: str, headers: Dict[str, str], body: str
               ) -> Tuple[int, Any, Dict[str, str]]:
        if not path.startswith(API_PREFIX):
            return 404, {"error": {"code": "", "message": "fake: unknown path"}}, {}
        rel = path[len(API_PREFIX):]
        base = "https://fake" + API_PREFIX
        try:
            if rel == "EntityDefinitions" and method == "POST":
                return self._create_table(json.loads(body), base)
            m = re.fullmatch(r"EntityDefinitions\(LogicalName='([^']+)'\)(/Attributes|/Keys)?", rel)
            if m:
                return self._metadata(method, m.group(1), m.group(2), json.loads(body) if body else None, base)
            if rel == "RelationshipDefinitions" and method == "POST":
                return self._create_relationship(json.loads(body), base)
            if rel == "PublishXml" and method == "POST":
                return 204, None, {}
            if rel == "$batch" and method == "POST":
                return self._batch(headers, body)
            m = re.fullmatch(r"([a-z0-9_]+)(\((.+)\))?", rel)
            if m:
                return self._data(method, m.group(1), m.group(3), query, headers, body, base)
        except FakeError as e:
            return e.status, {"error": {"code": "", "message": f"fake: {e}"}}, {}
        return 404, {"error": {"code": "", "message": f"fake: no route for {method} {rel}"}}, {}

    # ---------- metadata ----------
    def _create_table(self, meta: Dict[str, Any], base: str):
        logical = meta["SchemaName"].lower()
        if logical in self.tables:
            raise FakeError(400, f"table {logical} already exists")
        primary = [a for a in meta.get("Attributes", []) if a.get("IsPrimaryName")]
        if len(primary) != 1:
            raise FakeError(400, "the table needs exactly one primary name column in Attributes")
        coll = meta["DisplayCollectionName"]["LocalizedLabels"][0]["Label"]  # required property
        del coll
        entity_set = logical + "s"
        self.tables[logical] = {"meta": meta, "entity_set": entity_set,
                                "columns": {logical + "id": {"AttributeType": "Uniqueidentifier"}},
                                "keys": []}
        for a in meta["Attributes"]:
            self._add_column(logical, a)
        self.rows[entity_set] = {}
        mid = str(uuid.uuid4())
        return 204, None, {"OData-EntityId": f"{base}EntityDefinitions({mid})"}

    def _add_column(self, table: str, attr: Dict[str, Any]):
        name = attr["SchemaName"].lower()
        cols = self.tables[table]["columns"]
        if name in cols:
            raise FakeError(400, f"column {name} already exists")
        cols[name] = attr

    def _metadata(self, method: str, table: str, sub: Optional[str], body, base: str):
        if table not in self.tables:
            raise FakeError(404, f"table {table} not found")
        t = self.tables[table]
        if sub is None and method == "GET":
            return 200, {"LogicalName": table, "EntitySetName": t["entity_set"]}, {}
        if sub == "/Attributes" and method == "POST":
            self._add_column(table, body)
            return 204, None, {"OData-EntityId": f"{base}EntityDefinitions(LogicalName='{table}')/Attributes({uuid.uuid4()})"}
        if sub == "/Keys" and method == "POST":
            for col in body["KeyAttributes"]:
                if col not in t["columns"]:
                    raise FakeError(400, f"key column {col} doesn't exist")
            key = {"SchemaName": body["SchemaName"], "KeyAttributes": body["KeyAttributes"],
                   "EntityKeyIndexStatus": "Pending", "_polls": 0, "MetadataId": str(uuid.uuid4())}
            t["keys"].append(key)
            return 204, None, {"OData-EntityId": f"{base}EntityDefinitions(LogicalName='{table}')/Keys({key['MetadataId']})"}
        if sub == "/Keys" and method == "GET":
            out = []
            for k in t["keys"]:
                self._advance_key(k)
                out.append({x: k[x] for x in ("SchemaName", "KeyAttributes", "EntityKeyIndexStatus", "MetadataId")})
            return 200, {"value": out}, {}
        raise FakeError(405, f"{method} not supported on {sub}")

    def _advance_key(self, key: Dict[str, Any]):
        # Background index job: each poll moves it one step.
        if key["EntityKeyIndexStatus"] == "Active":
            return
        key["_polls"] += 1
        if key["_polls"] >= self.key_polls_until_active:
            key["EntityKeyIndexStatus"] = "Active"
        else:
            key["EntityKeyIndexStatus"] = "InProgress"

    def _create_relationship(self, rel: Dict[str, Any], base: str):
        if rel.get("@odata.type") != "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata":
            raise FakeError(400, "@odata.type must say which kind of relationship")
        child = rel["ReferencingEntity"]
        if child not in self.tables:
            raise FakeError(404, f"table {child} not found")
        lookup = dict(rel["Lookup"])
        lookup["_target"] = rel["ReferencedEntity"]
        self._add_column(child, lookup)
        return 204, None, {"OData-EntityId": f"{base}RelationshipDefinitions({uuid.uuid4()})"}

    # ---------- data ----------
    def _table_for_set(self, entity_set: str) -> Tuple[str, Dict[str, Any]]:
        for logical, t in self.tables.items():
            if t["entity_set"] == entity_set:
                return logical, t
        raise FakeError(404, f"entity set {entity_set} not found")

    def _data(self, method, entity_set, key_text, query, headers, body, base):
        logical, t = self._table_for_set(entity_set)
        rows = self.rows[entity_set]
        if method == "GET" and key_text is None:
            return self._query(logical, t, rows, query, headers, base, entity_set)
        if method == "PATCH" and key_text is not None:
            return self._upsert(logical, t, rows, entity_set, key_text, query, headers, json.loads(body or "{}"), base)
        if method == "POST" and key_text is None:
            data = json.loads(body)
            self._validate(t, data)
            rid = str(uuid.uuid4())
            rows[rid] = {logical + "id": rid, **data}
            return 204, None, {"OData-EntityId": f"{base}{entity_set}({rid})"}
        raise FakeError(405, f"{method} not supported here")

    def _validate(self, t: Dict[str, Any], data: Dict[str, Any]):
        for col, val in data.items():
            if col.endswith("@odata.bind"):
                continue
            meta = t["columns"].get(col)
            if meta is None:
                raise FakeError(400, f"property {col} doesn't exist on this table")
            if meta.get("AttributeType") == "Money" and val is not None and val < meta.get("MinValue", float("-inf")):
                raise FakeError(400, f"{col} is below its minimum value")
            if meta.get("AttributeType") == "String" and val is not None and len(val) > meta.get("MaxLength", 4000):
                raise FakeError(400, f"{col} is longer than {meta.get('MaxLength')}")
            if meta.get("AttributeType") == "Picklist" and val is not None:
                allowed = {o["Value"] for o in meta["OptionSet"]["Options"]}
                if val not in allowed:
                    raise FakeError(400, f"{val} isn't a valid option for {col}")

    def _parse_key(self, t, key_text: str) -> Dict[str, Any]:
        if re.fullmatch(r"[0-9a-fA-F-]{36}", key_text):
            return {"__id": key_text.lower()}
        parts = dict(re.findall(r"([a-z0-9_]+)=('(?:[^']|'')*'|[^,]+)", key_text))
        key = {k: (v[1:-1].replace("''", "'") if v.startswith("'") else json.loads(v)) for k, v in parts.items()}
        for k in t["keys"]:
            if sorted(k["KeyAttributes"]) == sorted(key):
                if k["EntityKeyIndexStatus"] != "Active":
                    raise FakeError(400, f"alternate key {k['SchemaName']} isn't Active yet ({k['EntityKeyIndexStatus']})")
                return key
        raise FakeError(400, f"no alternate key on columns {sorted(key)}")

    def _upsert(self, logical, t, rows, entity_set, key_text, query, headers, data, base):
        key = self._parse_key(t, key_text)
        if "__id" in key:
            match = rows.get(key["__id"])
        else:
            match = next((r for r in rows.values() if all(r.get(c) == v for c, v in key.items())), None)
        if headers.get("If-Match") == "*" and match is None:
            raise FakeError(404, "record does not exist")
        if headers.get("If-None-Match") == "*" and match is not None:
            raise FakeError(412, "a record with matching key values already exists")
        data = {k: v for k, v in data.items() if k not in key}     # key values in the body are ignored
        self._validate(t, data)
        created = match is None
        if created:
            rid = key.get("__id") or str(uuid.uuid4())
            match = {logical + "id": rid, **{k: v for k, v in key.items() if k != "__id"}}
            rows[rid] = match
        match.update(data)
        hdrs = {"OData-EntityId": f"{base}{entity_set}({key_text})"}
        if "return=representation" in headers.get("Prefer", ""):
            return (201 if created else 200), {logical + "id": match[logical + "id"]}, hdrs
        return 204, None, hdrs

    def _query(self, logical, t, rows, query, headers, base, entity_set):
        params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        if "$skip" in params:
            raise FakeError(400, "$skip isn't supported - use paging")
        m = re.search(r"odata\.maxpagesize=(\d+)", headers.get("Prefer", ""))
        page = min(int(m.group(1)), 5000) if m else 5000
        result = [r for r in rows.values() if _matches(r, params.get("$filter"))]
        if "$orderby" in params:
            col, _, direction = params["$orderby"].partition(" ")
            result.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=direction == "desc")
        if "$top" in params and not m:
            result = result[: int(params["$top"])]
        offset = 0
        if "$skiptoken" in params:
            offset = int(base64.urlsafe_b64decode(params["$skiptoken"]).decode())
        chunk = result[offset: offset + page]
        select = params.get("$select", "").split(",") if params.get("$select") else None
        out = [{c: r.get(c) for c in ([logical + "id"] + select)} if select else dict(r) for r in chunk]
        payload: Dict[str, Any] = {"value": out}
        if offset + page < len(result):
            token = base64.urlsafe_b64encode(str(offset + page).encode()).decode()
            clean = "&".join(f"{k}={v}" for k, v in params.items() if k != "$skiptoken")
            payload["@odata.nextLink"] = f"{base}{entity_set}?{clean}&$skiptoken={token}"
        return 200, payload, {}

    # ---------- $batch ----------
    def _batch(self, headers: Dict[str, str], body: str):
        ct = headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ct)
        if not m:
            raise FakeError(400, "batch needs a boundary")
        if "\r\n" not in body:
            raise FakeError(400, "batch payload must use CRLF line endings")
        continue_on_error = "odata.continue-on-error" in headers.get("Prefer", "")
        parts = _split(body, m.group(1))
        if len(parts) > 1000:
            raise FakeError(400, "more than 1,000 requests in one batch")
        out_id = f"batchresponse_{uuid.uuid4()}"
        out: List[str] = []
        for part in parts:
            head, _, rest = part.partition(CRLF + CRLF)
            nested = re.search(r'boundary="?([^";\r\n]+)"?', head)
            if nested:   # change set: all or nothing
                snapshot = copy.deepcopy((self.tables, self.rows))
                inner = _split(rest, nested.group(1))
                results = [self._run_inner(p) for p in inner]
                failed = next((r for r in results if r[0] >= 400), None)
                if failed:
                    self.tables, self.rows = snapshot
                    if not continue_on_error:
                        return failed[0], failed[1], {}
                    out.append(_render(out_id, [failed]))
                else:
                    cs_id = f"changesetresponse_{uuid.uuid4()}"
                    out.append(f"--{out_id}{CRLF}Content-Type: multipart/mixed; boundary={cs_id}{CRLF}{CRLF}"
                               + _render(cs_id, results) + f"--{cs_id}--{CRLF}")
            else:
                r = self._run_inner(part)
                if r[0] >= 400 and not continue_on_error:
                    return r[0], r[1], {}
                out.append(_render(out_id, [r]))
        text = "".join(out) + f"--{out_id}--{CRLF}"
        return 200, text, {"Content-Type": f"multipart/mixed; boundary={out_id}"}

    def _run_inner(self, part: str) -> Tuple[int, Any, Dict[str, str]]:
        _, _, http = part.partition(CRLF + CRLF)
        request_line, _, rest = http.partition(CRLF)
        method, url, _ = request_line.split(" ", 2)
        hdr_block, _, body = rest.partition(CRLF + CRLF)
        hdrs = dict(line.split(": ", 1) for line in hdr_block.split(CRLF) if ": " in line)
        sp = urlsplit(url)
        return self.handle(method, unquote(sp.path), unquote(sp.query), hdrs, body.strip())


class FakeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _split(body: str, boundary: str) -> List[str]:
    chunks = body.split(f"--{boundary}")
    return [c.strip(CRLF) for c in chunks[1:] if c.strip(CRLF) and not c.startswith("--")]


def _render(boundary: str, results) -> str:
    text = ""
    for status, payload, headers in results:
        reason = {200: "OK", 201: "Created", 204: "No Content"}.get(status, "Error")
        lines = [f"--{boundary}", "Content-Type: application/http", "Content-Transfer-Encoding: binary", "",
                 f"HTTP/1.1 {status} {reason}"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        lines.append("")
        lines.append(json.dumps(payload) if payload is not None else "")
        text += CRLF.join(lines) + CRLF
    return text


_COND = re.compile(r"([a-z0-9_]+) (eq|ne|gt|ge|lt|le) ('(?:[^']|'')*'|null|-?\d+(?:\.\d+)?)")


def _matches(row: Dict[str, Any], flt: Optional[str]) -> bool:
    if not flt:
        return True
    for cond in flt.split(" and "):
        m = _COND.fullmatch(cond.strip())
        if not m:
            raise FakeError(400, f"fake filter parser doesn't understand {cond!r}")
        col, op, raw = m.groups()
        val: Any = None if raw == "null" else (raw[1:-1].replace("''", "'") if raw.startswith("'") else float(raw))
        cur = row.get(col)
        if op in ("eq", "ne"):
            ok = (cur == val) if op == "eq" else (cur != val)
        else:
            if cur is None or val is None:
                return False
            ok = {"gt": cur > val, "ge": cur >= val, "lt": cur < val, "le": cur <= val}[op]
        if not ok:
            return False
    return True
