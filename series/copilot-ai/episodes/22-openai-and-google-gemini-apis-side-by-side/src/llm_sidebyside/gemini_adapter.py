"""Gemini Interactions API adapter. Stateless: store=false, so every turn resends the steps the model needs."""
from __future__ import annotations

import json
import os
from typing import Optional

from google import genai
from google.genai import types
from google.genai._interactions_errors import GeminiNextGenAPIClientError

from . import contract
from .dialects import gemini_request
from .errors import RunError, classify, with_retry
from .models import Outcome, Usage

DEFAULT_MODEL = "gemini-3.8-flash"
STATUS = {"completed": "complete", "incomplete": "truncated", "requires_action": "complete"}


def build_client(api_key: Optional[str] = None, http_client=None, env=None):
    env = os.environ if env is None else env
    key = api_key or env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if not key:
        raise RunError("GEMINI_API_KEY is not set (type it in your own shell, never in a file)")
    # attempts=1: the SDK's own retries are off so with_retry in errors.py is the only retry policy (same as OpenAI max_retries=0)
    opts = types.HttpOptions(httpx_client=http_client, retry_options=types.HttpRetryOptions(attempts=1))
    return genai.Client(api_key=key, http_options=opts)


def _usage(resp) -> Usage:
    u = resp.usage
    if u is None:
        return Usage()
    return Usage(
        input_tokens=u.total_input_tokens or 0,
        output_tokens=u.total_output_tokens or 0,
        reasoning_tokens=u.total_thought_tokens or 0,
        cached_tokens=u.total_cached_tokens or 0,
    )


def _create(client, body: dict):
    def call():
        try:
            return client.interactions.create(**body)
        except GeminiNextGenAPIClientError as exc:
            raise classify("gemini", exc) from exc
    return with_retry(call)


def _outcome(resp, model: str, usage: Usage, requests: int, tools=None) -> Outcome:
    status = STATUS.get(resp.status, "failed")
    return Outcome("gemini", model, status, text=resp.output_text or "", usage=usage, requests=requests, tool_calls=tools or [])


def run_extract(client, model: str = DEFAULT_MODEL) -> Outcome:
    body = gemini_request(model, contract.SYSTEM, contract.EXTRACT_PROMPT, schema=contract.EXTRACT_SCHEMA)
    resp = _create(client, body)
    out = _outcome(resp, model, _usage(resp), 1)
    if out.status == "complete":
        try:
            out.parsed = json.loads(out.text)
        except json.JSONDecodeError as exc:
            out.problems.append(f"not JSON: {exc}")
            return out
        # Gemini accepts minLength / uniqueItems and does not enforce them, so this check is not optional.
        out.problems = contract.check_extract(out.parsed)
    return out


def run_truncate(client, model: str = DEFAULT_MODEL) -> Outcome:
    body = gemini_request(model, contract.SYSTEM, contract.TRUNCATE_PROMPT, max_output_tokens=contract.TRUNCATE_MAX_TOKENS)
    resp = _create(client, body)
    return _outcome(resp, model, _usage(resp), 1)


def run_tool(client, model: str, data: dict, max_turns: int = 4) -> Outcome:
    body = gemini_request(model, contract.SYSTEM, contract.TOOL_PROMPT, tool=contract.TOOL_SPEC)
    total, calls = Usage(), []
    for turn in range(1, max_turns + 1):
        resp = _create(client, body)
        total.add(_usage(resp))
        pending = [s for s in resp.steps if s.type == "function_call"]
        if not pending:
            return _outcome(resp, model, total, turn, calls)
        # stateless: send back the model's own steps (thought signatures included), then one result per call
        body["input"] = list(body["input"]) + [s.model_dump(mode="json", exclude_none=True) for s in resp.steps]
        for call in pending:
            calls.append(call.name)
            try:
                result = json.dumps(contract.get_vendor_renewals(data, **call.arguments))
                is_error = False
            except (ValueError, TypeError) as exc:
                result, is_error = json.dumps({"error": str(exc)}), True
            body["input"].append({"type": "function_result", "call_id": call.id, "name": call.name,
                                  "result": result, "is_error": is_error})
    return Outcome("gemini", model, "failed", usage=total, requests=max_turns, tool_calls=calls,
                   problems=[f"no final answer after {max_turns} turns"])
