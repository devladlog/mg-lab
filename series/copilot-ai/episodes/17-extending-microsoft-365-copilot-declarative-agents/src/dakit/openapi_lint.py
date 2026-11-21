"""Lint an OpenAPI description for use as an API plugin.

Rules come from Learn: "Create effective OpenAPI descriptions for extending Microsoft 365 Copilot" (descriptions,
operationId) and the Known issues page (unsupported OpenAPI features). A structural check with
openapi-spec-validator runs first, as Learn recommends validating against the OpenAPI Specification."""
from __future__ import annotations

from pathlib import Path

import yaml
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from .findings import Finding

METHODS = {"get", "put", "post", "delete", "patch", "head", "options"}


def _resolve(spec: dict, node: object, seen: tuple[str, ...] = ()) -> object:
    if isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            return {"__cycle__": ref}
        target = spec
        for part in ref.lstrip("#/").split("/"):
            target = target[part]
        return _resolve(spec, target, seen + (ref,))
    return node


def _walk(spec: dict, node: object, path: str, seen: tuple[str, ...], hits: list[tuple[str, str]]):
    """Collect (path, keyword) for oneOf/allOf/anyOf and cycles, following $ref."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in seen:
                hits.append((path, "circular reference " + ref))
                return
            _walk(spec, _resolve(spec, node), path, seen + (ref,), hits)
            return
        for key, value in node.items():
            if key in {"oneOf", "allOf", "anyOf"}:
                hits.append((path, key))
            _walk(spec, value, f"{path}/{key}", seen, hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(spec, v, f"{path}[{i}]", seen, hits)


def _has_nested_object(spec: dict, schema: object, depth: int = 0, seen: tuple[str, ...] = ()) -> bool:
    """True when an object schema has a property that is itself an object (arrays of scalars are fine)."""
    schema = _resolve(spec, schema, seen)
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "object" or "properties" in schema:
        for sub in (schema.get("properties") or {}).values():
            sub = _resolve(spec, sub)
            if isinstance(sub, dict) and (sub.get("type") == "object" or "properties" in sub):
                return True
            if isinstance(sub, dict) and sub.get("type") == "array":
                item = _resolve(spec, sub.get("items", {}))
                if isinstance(item, dict) and (item.get("type") == "object" or "properties" in item):
                    return True
    return False


def lint_openapi(path: Path) -> list[Finding]:
    path = Path(path)
    out: list[Finding] = []
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return [Finding("error", path.name, f"cannot read: {e}")]
    try:
        validate(spec)
    except OpenAPIValidationError as e:
        out.append(Finding("error", path.name, f"not a valid OpenAPI description: {str(e)[:200]}"))
        return out
    except Exception as e:  # unknown version etc.
        out.append(Finding("error", path.name, f"cannot validate: {str(e)[:200]}"))
        return out

    if not (spec.get("info") or {}).get("description"):
        out.append(Finding("error", "info.description", "missing: Copilot needs it to know what the API does and when to use the plugin"))
    servers = spec.get("servers") or []
    if not servers:
        out.append(Finding("error", "servers", "no server URL: Copilot needs to know where to call"))
    for s in servers:
        if not str(s.get("url", "")).startswith("https://"):
            out.append(Finding("warning", "servers", f"server {s.get('url')} is not https"))

    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    for name, sch in schemes.items():
        if sch.get("type") == "apiKey" and sch.get("in") == "cookie":
            out.append(Finding("error", f"securitySchemes.{name}", "API keys in cookies are not supported (Learn: Known issues)"))
        if sch.get("type") == "apiKey" and sch.get("in") in {"header", "query"}:
            out.append(Finding("warning", f"securitySchemes.{name}",
                               "Learn's API key page lists custom header and query parameter keys, its Known issues page lists them as unsupported: prefer http bearer, or test it"))
        for flow in (sch.get("flows") or {}):
            if flow not in {"authorizationCode"}:
                out.append(Finding("error", f"securitySchemes.{name}", f"OAuth flow {flow} is not supported (Learn: only authorization code, with or without PKCE)"))

    seen_ids: set[str] = set()
    for p, item in (spec.get("paths") or {}).items():
        for method, op in item.items():
            if method.lower() not in METHODS:
                continue
            where = f"{method.upper()} {p}"
            op_id = op.get("operationId")
            if not op_id:
                out.append(Finding("error", where, "no operationId: Copilot builds its functions from operation ids"))
            elif op_id in seen_ids:
                out.append(Finding("error", where, f"operationId {op_id} is used twice"))
            else:
                seen_ids.add(op_id)
            if not (op.get("description") or op.get("summary")):
                out.append(Finding("error", where, "no summary or description: Copilot picks endpoints by their descriptions"))
            elif not op.get("description"):
                out.append(Finding("warning", where, "only a summary: add a description that says when to use the operation"))
            for prm in op.get("parameters", []):
                prm = _resolve(spec, prm)
                if not prm.get("description"):
                    out.append(Finding("error", f"{where} parameter {prm.get('name')}", "no description: Copilot uses it to fill the parameter from the prompt"))
                if _has_nested_object(spec, prm.get("schema", {})):
                    out.append(Finding("error", f"{where} parameter {prm.get('name')}", "nested objects in parameters are not supported (Learn: Known issues)"))
            for media in ((op.get("requestBody") or {}).get("content") or {}).values():
                if _has_nested_object(spec, media.get("schema", {})):
                    out.append(Finding("error", f"{where} requestBody", "nested objects in request bodies are not supported (Learn: Known issues)"))
            if not op.get("responses"):
                out.append(Finding("error", where, "no responses"))
            for code, resp in (op.get("responses") or {}).items():
                resp = _resolve(spec, resp)
                if not resp.get("description"):
                    out.append(Finding("error", f"{where} response {code}", "no description"))
            if not any(str(c).startswith(("4", "5")) for c in (op.get("responses") or {})):
                out.append(Finding("warning", where, "no error response documented (Learn: define success and error responses)"))

    hits: list[tuple[str, str]] = []
    _walk(spec, spec.get("paths", {}), "paths", (), hits)
    for where, kw in hits:
        if kw.startswith("circular"):
            out.append(Finding("error", where, f"{kw}: not supported, use a flattened schema (Learn: Known issues)"))
        else:
            out.append(Finding("error", where, f"{kw} is not supported in API plugins, use a flattened schema (Learn: Known issues)"))
    return out
