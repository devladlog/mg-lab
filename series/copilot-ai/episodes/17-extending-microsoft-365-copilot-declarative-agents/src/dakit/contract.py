"""Contract test: call the real Vendor Renewals API code through its WSGI interface and check every answer
against the response schemas of the OpenAPI description that the plugin hands to Copilot."""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .findings import Finding


def _validator_for(spec: dict, schema: dict) -> Draft202012Validator:
    # OpenAPI 3.0 schemas are close enough to JSON Schema for these simple models; $ref resolves inside the spec.
    registry = Registry().with_resource("urn:spec", Resource.from_contents({"$schema": "https://json-schema.org/draft/2020-12/schema", **spec}))
    return Draft202012Validator({"$ref": "urn:spec" + schema["$ref"]} if "$ref" in schema else schema, registry=registry)


def call(app, method: str, path: str, query: str = "", body: object | None = None, key: str | None = "k"):
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "SERVER_NAME": "t", "SERVER_PORT": "0",
           "wsgi.input": io.BytesIO(b""), "CONTENT_LENGTH": "0", "wsgi.url_scheme": "http"}
    if key is not None:
        env["HTTP_AUTHORIZATION"] = f"Bearer {key}"
    if body is not None:
        raw = json.dumps(body).encode()
        env["wsgi.input"], env["CONTENT_LENGTH"] = io.BytesIO(raw), str(len(raw))
    status = {}
    chunks = app(env, lambda s, h: status.setdefault("s", s))
    return int(status["s"].split()[0]), json.loads(b"".join(chunks))


def run_contract(openapi_path: Path, app) -> list[Finding]:
    """Every documented example request is sent; the status must be documented and the body must fit its schema."""
    spec = yaml.safe_load(Path(openapi_path).read_text(encoding="utf-8"))
    out: list[Finding] = []

    def check(label, method, path, query, body, key, expect_status):
        status, payload = call(app, method, path, query, body, key)
        op_path = _template(spec, path)
        responses = spec["paths"][op_path][method.lower()]["responses"]
        resp = responses.get(str(status))
        if status != expect_status:
            out.append(Finding("error", label, f"expected HTTP {expect_status}, got {status}: {payload}"))
            return
        if resp is None:
            out.append(Finding("error", label, f"HTTP {status} is not documented in the OpenAPI description"))
            return
        ref = resp.get("$ref")
        if ref:
            resp = spec["components"]["responses"][ref.split("/")[-1]]
        schema = resp["content"]["application/json"]["schema"]
        for err in _validator_for(spec, schema).iter_errors(payload):
            out.append(Finding("error", label, f"response does not match its schema: {err.message[:200]}"))

    check("GET /renewals", "GET", "/renewals", "", None, "k", 200)
    check("GET /renewals?withinDays=180&owner=Jordan Demo", "GET", "/renewals", "withinDays=180&owner=Jordan%20Demo", None, "k", 200)
    check("GET /renewals?withinDays=0 (400)", "GET", "/renewals", "withinDays=0", None, "k", 400)
    check("GET /renewals without key (401)", "GET", "/renewals", "", None, None, 401)
    check("GET /vendors/fabrikam-cloud", "GET", "/vendors/fabrikam-cloud", "", None, "k", 200)
    check("GET /vendors/none (404)", "GET", "/vendors/none", "", None, "k", 404)
    ex = spec["paths"]["/vendors/{vendorId}/reminders"]["post"]["requestBody"]["content"]["application/json"]["example"]
    check("POST reminders (documented example)", "POST", "/vendors/fabrikam-cloud/reminders", "", ex, "k", 201)
    check("POST reminders late date (400)", "POST", "/vendors/fabrikam-cloud/reminders", "", {"remindOn": "2027-02-01"}, "k", 400)
    check("POST reminders unknown vendor (404)", "POST", "/vendors/none/reminders", "", ex, "k", 404)
    return out


def _template(spec: dict, path: str) -> str:
    if path in spec["paths"]:
        return path
    for tpl in spec["paths"]:
        a, b = tpl.strip("/").split("/"), path.strip("/").split("/")
        if len(a) == len(b) and all(x.startswith("{") or x == y for x, y in zip(a, b)):
            return tpl
    raise KeyError(path)
