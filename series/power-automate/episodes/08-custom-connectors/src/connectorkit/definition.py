"""Static checks for the three connector files (apiDefinition.swagger.json, apiProperties.json, settings.json).

Every rule names where it comes from:
  [swagger]  the OpenAPI 2.0 JSON schema (schemas/swagger-2.0.schema.json)
  [limits]   Learn, custom connector FAQ: definition file under 1 MB, at most 256 operations (Logic Apps table)
  [cert]     Learn, "Prepare ... connector files for certification": title, description, summaries, responses.
             These are certification requirements: a private connector works without them, we follow them anyway.
  [ext]      Learn, "Create a custom connector with an OpenAPI extension": x-ms-visibility, x-ms-trigger, ...
  [webhook]  Learn, "Use a webhook as a trigger": the create operation, x-ms-notification-content,
             x-ms-notification-url, the delete operation, the Location header
  [auth]     Learn, certification page: the connection parameter shapes for Basic, API key and OAuth
  [policy]   Learn, policy templates: the setheader template and its keys
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schemas" / "swagger-2.0.schema.json"
MAX_BYTES = 1024 * 1024
MAX_OPERATIONS = 256
VISIBILITY = {"important", "advanced", "internal"}
TRIGGER_KINDS = {"single", "batch"}
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch"}
POWER_PLATFORM_WORDS = ("power apps", "power automate", "power platform", "copilot studio")
SETHEADER_KEYS = {"x-ms-apimTemplateParameter.name", "x-ms-apimTemplateParameter.value",
                  "x-ms-apimTemplateParameter.existsAction", "x-ms-apimTemplate-policySection",
                  "x-ms-apimTemplate-operationName"}
EXISTS_ACTIONS = {"override", "skip", "append"}
POLICY_SECTIONS = {"Request", "Response", "Failure"}


@dataclass
class Finding:
    severity: str       # error | warning
    where: str
    message: str

    def __str__(self):
        return f"{self.severity.upper():7} {self.where}: {self.message}"


@dataclass
class Connector:
    definition: dict
    properties: dict
    settings: dict = field(default_factory=dict)
    size_bytes: int = 0

    @property
    def operations(self) -> dict[str, tuple[str, str, dict]]:
        """operationId -> (path, method, operation)"""
        out = {}
        for path, item in self.definition.get("paths", {}).items():
            for method, op in item.items():
                if method in HTTP_METHODS and isinstance(op, dict) and "operationId" in op:
                    out[op["operationId"]] = (path, method, op)
        return out

    @property
    def triggers(self) -> dict[str, tuple[str, str, dict]]:
        return {k: v for k, v in self.operations.items() if "x-ms-trigger" in v[2]}


def load_connector(folder: str | Path) -> Connector:
    folder = Path(folder)
    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8")) if (folder / "settings.json").exists() else {}
    api_file = folder / settings.get("apiDefinition", "apiDefinition.swagger.json")
    prop_file = folder / settings.get("apiProperties", "apiProperties.json")
    raw = api_file.read_bytes()
    return Connector(json.loads(raw), json.loads(prop_file.read_text(encoding="utf-8")), settings, len(raw))


def resolve(definition: dict, node):
    """Follow a $ref."""
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        cur = definition
        for part in ref[2:].split("/"):
            cur = cur[part]
        node = cur
    return node


def _walk_schema(definition: dict, schema, path="", seen=()):
    """Yield (path, property schema) for every property of an object schema, following $ref."""
    schema = resolve(definition, schema)
    if not isinstance(schema, dict):
        return
    ref_id = id(schema)
    if ref_id in seen:
        return
    for name, prop in (schema.get("properties") or {}).items():
        prop = resolve(definition, prop)
        yield f"{path}/{name}", prop
        yield from _walk_schema(definition, prop, f"{path}/{name}", seen + (ref_id,))
    if "items" in schema:
        yield from _walk_schema(definition, schema["items"], path + "[]", seen + (ref_id,))


def _text_ok(s: str) -> bool:
    return bool(s) and s.rstrip()[-1] in ".!?"


def validate(c: Connector) -> list[Finding]:
    out: list[Finding] = []
    err = lambda w, m: out.append(Finding("error", w, m))
    warn = lambda w, m: out.append(Finding("warning", w, m))
    d = c.definition

    # [swagger] [limits]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for e in sorted(jsonschema.Draft4Validator(schema).iter_errors(d), key=lambda e: list(map(str, e.path))):
        err("swagger", f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message[:140]}")
    if c.size_bytes >= MAX_BYTES:
        err("limits", f"definition is {c.size_bytes} bytes; it must be less than 1 MB")
    ops = c.operations
    if len(ops) > MAX_OPERATIONS:
        err("limits", f"{len(ops)} operations; the limit is {MAX_OPERATIONS}")
    if d.get("swagger") != "2.0":
        err("swagger", "only OpenAPI 2.0 is supported (no OpenAPI 3)")
    if d.get("schemes") != ["https"]:
        err("swagger", f"schemes must be ['https'], found {d.get('schemes')}")

    # [cert] title, description
    info = d.get("info", {})
    title = info.get("title", "")
    if len(title) > 30:
        err("info.title", f"{len(title)} characters; certification allows 30")
    if re.search(r"\b(api|connector)\b", title, re.I) or any(w in title.lower() for w in POWER_PLATFORM_WORDS):
        err("info.title", "the title can't contain the words API, Connector or a Power Platform product name")
    desc = info.get("description", "")
    if not 30 < len(desc) < 500:
        err("info.description", f"{len(desc)} characters; it must be longer than 30 and shorter than 500")
    if any(w in desc.lower() for w in POWER_PLATFORM_WORDS):
        err("info.description", "no Power Platform product names in the description")

    ids = [op["operationId"] for _, _, op in ops.values()]
    if len(ids) != len(set(ids)):
        err("operations", "operationId values must be unique")

    for oid, (path, method, op) in ops.items():
        where = f"{method.upper()} {path} ({oid})"
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", oid):
            err(where, "operationId should be PascalCase without hyphens or spaces")
        summary, description = op.get("summary", ""), op.get("description", "")
        if not summary or not description:
            err(where, "every operation needs a summary and a description [cert]")
        if summary and (len(summary) > 80 or not re.fullmatch(r"[A-Za-z0-9() ]+", summary)):
            err(where, f"summary {summary!r}: at most 80 characters, letters, digits, spaces and parentheses only [cert]")
        if summary and summary == description:
            err(where, "summary and description are the same text")
        if description and not _text_ok(description):
            err(where, "the description should be a full sentence that ends with punctuation [cert]")
        vis = op.get("x-ms-visibility")
        if vis is None:
            err(where, "no x-ms-visibility (important, advanced or internal) [cert checklist]")
        elif vis not in VISIBILITY:
            err(where, f"x-ms-visibility {vis!r} isn't one of {sorted(VISIBILITY)} [ext]")
        responses = op.get("responses", {})
        if not any(code.startswith("2") for code in responses):
            err(where, "no 2xx response")
        for code, r in responses.items():
            if code == "default" and "schema" in r:
                err(where, "don't use a default response with an exact schema [cert]")
            if code.startswith("2") and code != "204" and "schema" not in r:
                err(where, f"{code} response has no schema: makers get no dynamic content [cert]")
        for prm in op.get("parameters", []):
            _check_param(where, prm, err)

    # definitions: every property described, visibility valid
    for name, schema_def in d.get("definitions", {}).items():
        for ppath, prop in _walk_schema(d, schema_def, name):
            if prop.get("x-ms-visibility", "important") not in VISIBILITY:
                err(f"definitions {ppath}", f"bad x-ms-visibility {prop['x-ms-visibility']!r}")

    _check_webhooks(c, err, warn)
    _check_properties(c, err, warn)
    _check_capabilities(c, err)
    return out


def _check_param(where, prm, err):
    pw = f"{where} parameter {prm.get('name')!r}"
    if prm.get("in") == "body":
        return
    if not prm.get("x-ms-summary"):
        err(pw, "no x-ms-summary (the title makers see) [ext]")
    if not prm.get("description"):
        err(pw, "no description [cert]")
    elif not _text_ok(prm["description"]):
        err(pw, "the description should end with punctuation [cert]")
    vis = prm.get("x-ms-visibility")
    if vis is not None and vis not in VISIBILITY:
        err(pw, f"x-ms-visibility {vis!r} [ext]")
    if vis == "internal" and prm.get("required") and "default" not in prm:
        err(pw, "an internal required parameter must have a default value [ext]")
    if prm.get("in") == "path" and prm.get("x-ms-url-encoding", "single") not in ("single", "double"):
        err(pw, "x-ms-url-encoding is single or double [ext]")


def _body_schema_props(d, op):
    for prm in op.get("parameters", []):
        if prm.get("in") == "body":
            yield from _walk_schema(d, prm.get("schema", {}))


def _internal_required_without_default(d, op):
    def walk(schema, path):
        schema = resolve(d, schema)
        req = set(schema.get("required", []))
        for name, prop in (schema.get("properties") or {}).items():
            prop = resolve(d, prop)
            if name in req and prop.get("x-ms-visibility") == "internal" and "default" not in prop \
                    and not prop.get("x-ms-notification-url") and prop.get("type") != "object":
                yield f"{path}/{name}", "required and internal, but no default value"
            yield from walk(prop, f"{path}/{name}")
    for prm in op.get("parameters", []):
        if prm.get("in") == "body":
            yield from walk(prm.get("schema", {}), prm["name"])


def _check_webhooks(c: Connector, err, warn):
    d = c.definition
    for oid, (path, method, op) in c.triggers.items():
        where = f"trigger {oid}"
        if op["x-ms-trigger"] not in TRIGGER_KINDS:
            err(where, f"x-ms-trigger is {sorted(TRIGGER_KINDS)} [ext]")
        item = d["paths"][path]
        if method != "post":
            err(where, "a webhook trigger registers itself with POST [webhook]")
        has_url = any(prop.get("x-ms-notification-url") is True for _, prop in _body_schema_props(d, op))
        is_webhook = "x-ms-notification-content" in item or has_url
        if not is_webhook:
            continue  # a polling trigger: nothing more to check here
        if "x-ms-notification-content" not in item:
            err(where, f"no x-ms-notification-content next to the operation in {path}: makers would get no dynamic content [webhook]")
            continue
        content = item["x-ms-notification-content"]
        if "schema" not in content:
            err(where, "x-ms-notification-content needs a schema [webhook]")
        urls = [p for p, prop in _body_schema_props(d, op) if prop.get("x-ms-notification-url") is True]
        if len(urls) != 1:
            err(where, f"exactly one body field must have x-ms-notification-url: true, found {len(urls)} [webhook]")
        for p, prop in _body_schema_props(d, op):
            if prop.get("x-ms-notification-url") and prop.get("x-ms-visibility") != "internal":
                warn(where, f"{p}: the callback URL field should be internal: makers never type it [webhook]")
        if not any(code == "201" for code in op.get("responses", {})):
            err(where, "the create operation should answer 201 (GitHub does) [webhook]")
        # the delete operation: same host, a path that extends the create path by one parameter
        deletes = [(p, o) for oid2, (p, m, o) in c.operations.items()
                   if m == "delete" and p.startswith(path + "/{") and p.count("/") == path.count("/") + 1]
        if not deletes:
            err(where, f"no delete operation at {path}/{{id}}: the platform can't remove the webhook when the flow "
                       f"is turned off or deleted, and GitHub keeps delivering to a dead callback [webhook]")
        for p, o in deletes:
            if o.get("x-ms-visibility") != "internal":
                warn(f"delete {p}", "the delete operation is for the platform: x-ms-visibility internal")
            create_params = {x["name"] for x in op["parameters"] if x.get("in") == "path"}
            delete_params = {x["name"] for x in o["parameters"] if x.get("in") == "path"}
            if not create_params <= delete_params:
                err(f"delete {p}", f"needs the create operation's path parameters {sorted(create_params)} [webhook]")
        # required, internal body fields need defaults, or nobody can fill them [ext]
        for p, why in _internal_required_without_default(d, op):
            err(where, f"{p}: {why} [ext]")


def _check_properties(c: Connector, err, warn):
    d, props = c.definition, c.properties.get("properties", {})
    sec = d.get("securityDefinitions", {})
    conn = props.get("connectionParameters", {})
    kinds = {v.get("type") for v in sec.values()}
    if "basic" in kinds:
        if set(conn) != {"username", "password"}:
            err("apiProperties", f"basic authentication needs connection parameters username and password, found {sorted(conn)} [auth]")
        for k, v in conn.items():
            if v.get("type") != "securestring":
                err(f"apiProperties {k}", "type must be securestring [auth]")
            ui = v.get("uiDefinition", {})
            if not ui.get("displayName") or not ui.get("description"):
                err(f"apiProperties {k}", "uiDefinition needs displayName and description [auth]")
        if conn.get("password", {}).get("uiDefinition", {}).get("constraints", {}).get("clearText") is not False:
            err("apiProperties password", "the password field must not be shown in clear text (clearText false) [auth]")
    if "stackOwner" in props:
        err("apiProperties", "stackOwner blocks `paconn update` in your own environment (Learn, paconn limitations); "
                             "keep it only in the copy you submit for certification")
    declared_ops = set(c.operations)
    for i, pol in enumerate(props.get("policyTemplateInstances", [])):
        where = f"apiProperties policy #{i + 1} ({pol.get('title')})"
        if pol.get("templateId") != "setheader":
            warn(where, f"template {pol.get('templateId')!r} isn't checked here")
            continue
        prm = pol.get("parameters", {})
        unknown = set(prm) - SETHEADER_KEYS
        if unknown:
            err(where, f"unknown setheader keys {sorted(unknown)} [policy]")
        for k in ("x-ms-apimTemplateParameter.name", "x-ms-apimTemplateParameter.value", "x-ms-apimTemplate-policySection"):
            if k not in prm:
                err(where, f"missing {k} [policy]")
        if prm.get("x-ms-apimTemplateParameter.existsAction", "override") not in EXISTS_ACTIONS:
            err(where, "existsAction is override, skip or append [policy]")
        if prm.get("x-ms-apimTemplate-policySection") not in POLICY_SECTIONS:
            err(where, "policy section is Request, Response or Failure [policy]")
        for name in prm.get("x-ms-apimTemplate-operationName", []) or []:
            if name not in declared_ops:
                err(where, f"operationName {name!r} isn't an operation of the definition [policy]")
    if not props.get("iconBrandColor"):
        warn("apiProperties", "no iconBrandColor")


def _check_capabilities(c: Connector, err):
    cap = c.definition.get("x-ms-capabilities", {})
    t = cap.get("testConnection", {}).get("operationId")
    if t and t not in c.operations:
        err("x-ms-capabilities", f"testConnection operation {t!r} doesn't exist")
    if t and c.operations.get(t, ("", "", {}))[1] != "get":
        err("x-ms-capabilities", "the test-connection operation should be a GET with no parameters")


def errors(findings):
    return [f for f in findings if f.severity == "error"]
