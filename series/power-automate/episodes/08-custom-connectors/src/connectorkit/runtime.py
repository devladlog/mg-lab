"""Builds the HTTP request a connector operation sends, from the connector files, the way Learn documents it.

What is documented (and followed here):
- URL = host + basePath + path; path parameters are URL-encoded once (x-ms-url-encoding single, the default)
  or twice (double); query and header parameters from the definition.
- Basic authentication: the connection's username and password go in the Authorization header.
- x-ms-visibility internal: makers can't set the parameter, the default is used.
- x-ms-notification-url: the platform puts the flow's callback URL in that field when it registers the webhook.
- Policy templates (setheader): override / skip / append, run on Request, for the listed operations (none listed =
  every operation).
- Webhook triggers: POST to the create operation; the platform removes the webhook with DELETE on the Location
  header of the 201 response, using the same connection.

What is NOT claimed: how the platform joins values for existsAction "append" (not documented, so not implemented),
retry behaviour, or the exact bytes it sends. Those are checked in the lab tenant.
"""
from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote, unquote

from .definition import Connector, resolve


@dataclass
class Request:
    method: str
    url: str
    headers: dict = field(default_factory=dict)   # lower-case names
    body: object = None


@dataclass
class Response:
    status: int
    headers: dict = field(default_factory=dict)   # lower-case names
    body: object = None


@dataclass
class Connection:
    """What a maker types when creating a connection to a Basic authentication connector."""
    username: str
    password: str


@dataclass
class Subscription:
    operation_id: str
    inputs: dict
    callback_url: str
    created: Response
    location: str | None


class InputError(ValueError):
    """The maker's input doesn't fit the operation: the designer would refuse it before any call is made."""


class Runtime:
    def __init__(self, connector: Connector, transport: Callable[[Request], Response]):
        self.c = connector
        self.transport = transport
        self.sent: list[Request] = []

    # ------------------------------------------------------------------ request building
    def _url(self, path_template: str, params: list[dict], inputs: dict) -> str:
        d = self.c.definition
        path = path_template
        for prm in params:
            if prm.get("in") != "path":
                continue
            name = prm["name"]
            if name not in inputs:
                raise InputError(f"path parameter {name!r} is required")
            value = quote(str(inputs[name]), safe="")
            if prm.get("x-ms-url-encoding", "single") == "double":
                value = quote(value, safe="")
            path = path.replace("{" + name + "}", value)
        base = d.get("basePath", "/").rstrip("/")
        query = []
        for prm in params:
            if prm.get("in") == "query" and prm["name"] in inputs:
                query.append(f"{quote(prm['name'])}={quote(str(inputs[prm['name']]), safe='')}")
        return f"https://{d['host']}{base}{path}" + ("?" + "&".join(query) if query else "")

    def _fill_body(self, schema, value, callback_url, where="body"):
        d = self.c.definition
        schema = resolve(d, schema)
        if schema.get("x-ms-notification-url") is True:
            return callback_url
        if schema.get("type") == "object" or "properties" in schema:
            value = {} if value is None else copy.deepcopy(value)
            out = {}
            for name, prop in (schema.get("properties") or {}).items():
                prop = resolve(d, prop)
                given = value.get(name)
                if prop.get("x-ms-visibility") == "internal":
                    if given is not None and "default" in prop and given != prop["default"]:
                        pass  # makers can't set it: ignore what they gave
                    given = prop.get("default", given) if prop.get("type") != "object" else given
                elif given is None and "default" in prop:
                    given = prop["default"]
                filled = self._fill_body(prop, given, callback_url, f"{where}.{name}")
                if filled is not None:
                    out[name] = filled
            for name in schema.get("required", []):
                if name not in out:
                    raise InputError(f"{where}.{name} is required")
            for name, v in value.items():
                if name not in (schema.get("properties") or {}):
                    out[name] = v
            return out
        return value

    def _auth_headers(self, conn: Connection) -> dict:
        sec = self.c.definition.get("securityDefinitions", {})
        if any(v.get("type") == "basic" for v in sec.values()):
            token = base64.b64encode(f"{conn.username}:{conn.password}".encode()).decode()
            return {"authorization": f"Basic {token}"}
        return {}

    def _policies(self, headers: dict, operation_id: str | None):
        for pol in self.c.properties.get("properties", {}).get("policyTemplateInstances", []):
            if pol.get("templateId") != "setheader":
                continue
            prm = pol["parameters"]
            if prm.get("x-ms-apimTemplate-policySection") != "Request":
                continue
            ops = prm.get("x-ms-apimTemplate-operationName") or []
            if ops and operation_id not in ops:
                continue
            name = prm["x-ms-apimTemplateParameter.name"].lower()
            action = prm.get("x-ms-apimTemplateParameter.existsAction", "override")
            if action == "append":
                raise NotImplementedError("existsAction append: the join isn't documented")
            if name in headers and action == "skip":
                continue
            headers[name] = prm["x-ms-apimTemplateParameter.value"]

    def build_request(self, operation_id: str, inputs: dict, conn: Connection, callback_url: str | None = None) -> Request:
        path, method, op = self.c.operations[operation_id]
        params = op.get("parameters", [])
        for prm in params:
            if prm.get("x-ms-visibility") == "internal" and prm.get("in") != "body":
                inputs = {**inputs, prm["name"]: prm.get("default", inputs.get(prm["name"]))}
        url = self._url(path, params, inputs)
        headers = {**self._auth_headers(conn)}
        for prm in params:
            if prm.get("in") == "header" and prm["name"] in inputs:
                headers[prm["name"].lower()] = str(inputs[prm["name"]])
        body = None
        for prm in params:
            if prm.get("in") == "body":
                body = self._fill_body(prm["schema"], inputs.get(prm["name"], inputs.get("body")), callback_url)
                headers["content-type"] = "application/json"
        self._policies(headers, operation_id)
        return Request(method.upper(), url, headers, body)

    # ------------------------------------------------------------------ calls
    def invoke(self, operation_id: str, inputs: dict, conn: Connection) -> Response:
        req = self.build_request(operation_id, inputs, conn)
        self.sent.append(req)
        return self.transport(req)

    def test_connection(self, conn: Connection) -> Response:
        op = self.c.definition.get("x-ms-capabilities", {}).get("testConnection", {}).get("operationId")
        if not op:
            raise InputError("the connector declares no testConnection operation")
        return self.invoke(op, {}, conn)

    def subscribe(self, operation_id: str, inputs: dict, conn: Connection, callback_url: str) -> Subscription:
        req = self.build_request(operation_id, inputs, conn, callback_url)
        self.sent.append(req)
        res = self.transport(req)
        location = res.headers.get("location") if res.status == 201 else None
        return Subscription(operation_id, inputs, callback_url, res, location)

    def unsubscribe(self, sub: Subscription, conn: Connection) -> Response | None:
        """What the platform does when the flow is turned off, edited or deleted. Without a Location header
        on the 201 response there is nothing to call (Learn: the API must include it)."""
        if not sub.location:
            return None
        op_id = None
        for oid, (path, method, _) in self.c.operations.items():
            if method == "delete" and _matches(path, unquote(sub.location.split("://", 1)[1].split("/", 1)[1])):
                op_id = oid
        if op_id is None:   # the definition has no delete operation: the platform has nothing to call
            return None
        headers = {**self._auth_headers(conn)}
        self._policies(headers, op_id)
        req = Request("DELETE", sub.location, headers)
        self.sent.append(req)
        return self.transport(req)


def _matches(template: str, path: str) -> bool:
    a, b = template.strip("/").split("/"), path.split("?")[0].strip("/").split("/")
    return len(a) == len(b) and all(x.startswith("{") or x == y for x, y in zip(a, b))
