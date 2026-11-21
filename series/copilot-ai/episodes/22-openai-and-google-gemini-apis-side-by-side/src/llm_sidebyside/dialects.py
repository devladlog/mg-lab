"""Pure functions: the canonical task -> each vendor's request body. No network, no SDK.

The adapters send exactly these dicts, so what `python -m llm_sidebyside payloads` prints is what goes over the wire.

OpenAI (Responses API, POST /v1/responses; Structured Outputs guide):
  * `text.format = {type: json_schema, name, schema, strict: true}`
  * strict mode needs every property in `required`, `additionalProperties: false` on every object, and optional fields
    modelled as a union with null; only a subset of JSON Schema is supported (pattern, format, minimum/maximum,
    minItems/maxItems, enum, anyOf ...).
Google Gemini (Interactions API, POST /v1/interactions; Structured outputs guide):
  * `response_format = {type: text, mime_type: application/json, schema}`
  * optional fields are plain; `minLength`, `maxLength`, `minProperties`, `maxProperties`, `uniqueItems`, `contains`,
    `minContains`, `maxContains` are accepted but ignored by constrained decoding, so validate them in your code.
"""
from __future__ import annotations

import copy
from typing import Optional

# Keywords outside OpenAI's documented Structured Outputs subset that this canonical schema can contain.
OPENAI_UNSUPPORTED = ("minLength", "maxLength", "minProperties", "maxProperties", "uniqueItems", "contains", "minContains", "maxContains")
# Gemini: accepted but not enforced (documented under "Limitations").
GEMINI_UNENFORCED = OPENAI_UNSUPPORTED


def _walk(node, path, fn):
    if isinstance(node, dict):
        fn(node, path)
        for key, val in node.items():
            if key == "properties" and isinstance(val, dict):
                for name, sub in val.items():
                    _walk(sub, f"{path}.{name}" if path else name, fn)
            elif key == "items":
                _walk(val, f"{path}[]", fn)
            elif key in ("anyOf", "allOf", "oneOf") and isinstance(val, list):
                for i, sub in enumerate(val):
                    _walk(sub, f"{path}.{key}[{i}]", fn)


def to_openai_strict(schema: dict) -> tuple[dict, dict]:
    """Return (strict schema, report). Report lists what was changed so nothing is silent."""
    out = copy.deepcopy(schema)
    report = {"made_nullable": [], "dropped_keywords": [], "closed_objects": []}

    def fix(node, path):
        for kw in OPENAI_UNSUPPORTED:
            if kw in node:
                report["dropped_keywords"].append((path or "(root)", kw))
                del node[kw]
        if node.get("type") == "object" and "properties" in node:
            required = set(node.get("required", []))
            for name, sub in node["properties"].items():
                if name not in required:
                    t = sub.get("type")
                    sub["type"] = [t, "null"] if isinstance(t, str) else sub.get("type")
                    report["made_nullable"].append(f"{path + '.' if path else ''}{name}")
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False
            report["closed_objects"].append(path or "(root)")

    _walk(out, "", fix)
    return out, report


def gemini_unenforced(schema: dict) -> list:
    """(path, keyword) pairs the schema contains that Gemini accepts but does not enforce."""
    found: list = []

    def look(node, path):
        found.extend((path or "(root)", kw) for kw in GEMINI_UNENFORCED if kw in node)

    _walk(schema, "", look)
    return found


# ---- tools ---------------------------------------------------------------------------------------------------------

def openai_tool(spec: dict) -> dict:
    params, _ = to_openai_strict(spec["parameters"])
    return {"type": "function", "name": spec["name"], "description": spec["description"], "parameters": params, "strict": True}


def gemini_tool(spec: dict) -> dict:
    return {"type": "function", "name": spec["name"], "description": spec["description"], "parameters": copy.deepcopy(spec["parameters"])}


# ---- request bodies ------------------------------------------------------------------------------------------------

def openai_request(model: str, system: str, prompt: str, *, schema: Optional[dict] = None, tool: Optional[dict] = None,
                   max_output_tokens: Optional[int] = None, name: str = "contoso_task") -> dict:
    body: dict = {
        "model": model,
        # GPT-6.2 appends top-level `instructions` after `input`; reusable instructions go first as a developer message
        "input": [{"role": "developer", "content": system}, {"role": "user", "content": prompt}],
        "store": False,  # Responses API keeps application state for 30 days unless store is false
    }
    if max_output_tokens is not None:
        body["max_output_tokens"] = max_output_tokens  # includes reasoning tokens; documented minimum 16
    if schema is not None:
        strict, _ = to_openai_strict(schema)
        body["text"] = {"format": {"type": "json_schema", "name": name, "schema": strict, "strict": True}}
    if tool is not None:
        body["tools"] = [openai_tool(tool)]
        body["include"] = ["reasoning.encrypted_content"]  # lets a stateless (store=false) tool loop keep the model's reasoning
    return body


def gemini_request(model: str, system: str, prompt: str, *, schema: Optional[dict] = None, tool: Optional[dict] = None,
                   max_output_tokens: Optional[int] = None) -> dict:
    body: dict = {
        "model": model,
        "system_instruction": system,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": prompt}]}],
        "store": False,  # Interactions are stored (1 day free tier, 55 days paid tier) unless store is false
    }
    if max_output_tokens is not None:
        body["generation_config"] = {"max_output_tokens": max_output_tokens}
    if schema is not None:
        body["response_format"] = {"type": "text", "mime_type": "application/json", "schema": copy.deepcopy(schema)}
    if tool is not None:
        body["tools"] = [gemini_tool(tool)]
    return body
