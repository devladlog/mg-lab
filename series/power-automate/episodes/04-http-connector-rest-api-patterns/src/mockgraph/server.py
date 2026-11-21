"""A small local stand-in for the two Microsoft endpoints the flow calls, for tests and the CLI demo.

It is NOT Microsoft Graph. It reproduces only the documented behaviour the flow depends on:

* client-credentials token endpoint: POST /{tenant}/oauth2/v2.0/token
* GET /v1.0/users with $select, $top (default 100, maximum 999), $expand=manager($select=...)
* server-side paging with an opaque @odata.nextLink that carries a $skiptoken; $skip isn't supported on /users
* 401 without a valid bearer token
* fault injection (429 with Retry-After, 503...) so retry policies can be tested on demand

Learn: https://learn.microsoft.com/graph/api/user-list  ·  https://learn.microsoft.com/graph/paging
       https://learn.microsoft.com/graph/api/user-list-manager  (GET /users?$expand=manager)
Error bodies use Graph's {"error": {"code", "message"}} shape; the codes and messages are the mock's own.
"""
from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit


@dataclass
class Fault:
    """Answer the next `times` matching requests with `status` (and an optional Retry-After)."""
    status: int
    page: int | None = None        # 1-based page of /v1.0/users; None = any page
    times: int = 1
    retry_after: int | None = None


@dataclass
class State:
    users: list[dict]
    tenant: str = "00000000-0000-0000-0000-000000000000"
    client_id: str = "00000000-0000-0000-0000-000000000001"
    client_secret: str = "lab-secret-not-real"
    faults: list[Fault] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)
    log: list[dict] = field(default_factory=list)   # every request: method, path, query, auth


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class _Handler(BaseHTTPRequestHandler):
    server_version = "mockgraph/1.0"
    state: State  # set on the class by serve()

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status: int, body: dict, headers: dict | None = None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(data)

    def _record(self, query: dict):
        self.state.log.append({"method": self.command, "path": urlsplit(self.path).path, "query": query,
                               "auth": self.headers.get("Authorization", "")})

    # ------------------------------------------------------------------ token endpoint
    def do_POST(self):
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        self._record({k: ("***" if k == "client_secret" else v) for k, v in form.items()})
        if parts.path != f"/{self.state.tenant}/oauth2/v2.0/token":
            return self._send(404, {"error": "not_found"})
        if form.get("grant_type") != "client_credentials":
            return self._send(400, {"error": "unsupported_grant_type"})
        if form.get("client_id") != self.state.client_id or form.get("client_secret") != self.state.client_secret:
            return self._send(401, {"error": "invalid_client", "error_description": "mock: wrong client id or secret"})
        token = "mock-" + secrets.token_hex(8)
        self.state.tokens.add(token)
        return self._send(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": token})

    # ------------------------------------------------------------------ users
    def do_GET(self):
        parts = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        self._record(query)
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] not in self.state.tokens:
            return self._send(401, _error("InvalidAuthenticationToken", "mock: missing or invalid bearer token"))
        if parts.path != "/v1.0/users":
            return self._send(404, _error("Request_ResourceNotFound", f"mock: no resource at {parts.path}"))
        if "$skip" in query:
            return self._send(400, _error("Request_BadRequest", "mock: $skip isn't supported on /users; follow @odata.nextLink"))
        try:
            top = int(query.get("$top", 100))
        except ValueError:
            return self._send(400, _error("Request_BadRequest", "mock: $top must be an integer"))
        if not 1 <= top <= 999:
            return self._send(400, _error("Request_BadRequest", "mock: $top must be between 1 and 999"))
        offset = int(base64.urlsafe_b64decode(query["$skiptoken"]).decode()) if "$skiptoken" in query else 0
        page = offset // top + 1
        for fault in self.state.faults:
            if fault.times > 0 and fault.page in (None, page):
                fault.times -= 1
                headers = {"Retry-After": fault.retry_after} if fault.retry_after is not None else {}
                return self._send(fault.status, _error("mockFault", f"mock: injected {fault.status}"), headers)
        selected = [self._shape(u, query) for u in self.state.users[offset:offset + top]]
        body = {"@odata.context": f"{self._base()}/v1.0/$metadata#users", "value": selected}
        if offset + top < len(self.state.users):
            nxt = dict(query)
            nxt["$skiptoken"] = base64.urlsafe_b64encode(str(offset + top).encode()).decode()
            body["@odata.nextLink"] = f"{self._base()}/v1.0/users?{urlencode(nxt, safe='$(),=;')}"
        return self._send(200, body)

    def _base(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def _shape(self, user: dict, query: dict) -> dict:
        fields = query.get("$select", "id,displayName,mail").split(",")
        out = {k: user.get(k) for k in fields}
        expand = query.get("$expand", "")
        if expand.startswith("manager"):
            manager = next((u for u in self.state.users if u["id"] == user.get("managerId")), None)
            if manager is not None:  # users without a manager have no 'manager' property in this mock
                out["manager"] = {"@odata.type": "#microsoft.graph.user", "id": manager["id"],
                                  "displayName": manager["displayName"]}
        return out


class MockGraph:
    """Run the mock on 127.0.0.1 in a background thread: `with MockGraph(users) as g: g.url`."""

    def __init__(self, users: list[dict], port: int = 0, **state):
        self.state = State(users=users, **state)
        handler = type("Handler", (_Handler,), {"state": self.state})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def graph_calls(self) -> list[dict]:
        return [r for r in self.state.log if r["path"] == "/v1.0/users"]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
