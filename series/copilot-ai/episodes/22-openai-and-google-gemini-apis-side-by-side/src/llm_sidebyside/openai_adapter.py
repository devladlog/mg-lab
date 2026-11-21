"""OpenAI Responses API adapter. Stateless: store=false, so every turn resends what the model needs."""
from __future__ import annotations

import json
import os
from typing import Optional

import openai

from . import contract
from .dialects import openai_request
from .errors import Failure, RunError, classify, with_retry
from .models import Outcome, Usage

DEFAULT_MODEL = "gpt-6.2-sol"


def build_client(api_key: Optional[str] = None, http_client=None, base_url: Optional[str] = None, env=None):
    env = os.environ if env is None else env
    key = api_key or env.get("OPENAI_API_KEY")
    if not key:
        raise RunError("OPENAI_API_KEY is not set (type it in your own shell, never in a file)")
    return openai.OpenAI(api_key=key, http_client=http_client, base_url=base_url, max_retries=0)


def _usage(resp) -> Usage:
    u = resp.usage
    if u is None:
        return Usage()
    return Usage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        reasoning_tokens=getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0,
        cached_tokens=getattr(u.input_tokens_details, "cached_tokens", 0) or 0,
    )


def _create(client, body: dict):
    def call():
        try:
            return client.responses.create(**body)
        except openai.OpenAIError as exc:
            raise classify("openai", exc) from exc
    return with_retry(call)


def _text_and_refusal(resp):
    text, refusal = [], None
    for item in resp.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text":
                    text.append(part.text)
                elif part.type == "refusal":
                    refusal = part.refusal
    return "".join(text), refusal


def _outcome(resp, model: str, usage: Usage, requests: int, tools=None) -> Outcome:
    text, refusal = _text_and_refusal(resp)
    if refusal is not None:
        status = "refused"
        text = refusal
    elif resp.status == "incomplete":
        status = "truncated"   # incomplete_details.reason: max_output_tokens or content_filter
    elif resp.status == "completed":
        status = "complete"
    else:
        status = "failed"
    return Outcome("openai", model, status, text=text, usage=usage, requests=requests, tool_calls=tools or [])


def run_extract(client, model: str = DEFAULT_MODEL) -> Outcome:
    body = openai_request(model, contract.SYSTEM, contract.EXTRACT_PROMPT, schema=contract.EXTRACT_SCHEMA)
    resp = _create(client, body)
    out = _outcome(resp, model, _usage(resp), 1)
    if out.status == "complete":
        try:
            out.parsed = json.loads(out.text)
        except json.JSONDecodeError as exc:
            out.problems.append(f"not JSON: {exc}")
            return out
        out.problems = contract.check_extract(out.parsed)   # strict mode does not check minLength / uniqueItems / arithmetic
    return out


def run_truncate(client, model: str = DEFAULT_MODEL) -> Outcome:
    body = openai_request(model, contract.SYSTEM, contract.TRUNCATE_PROMPT, max_output_tokens=contract.TRUNCATE_MAX_TOKENS)
    resp = _create(client, body)
    return _outcome(resp, model, _usage(resp), 1)


def run_tool(client, model: str, data: dict, max_turns: int = 4) -> Outcome:
    body = openai_request(model, contract.SYSTEM, contract.TOOL_PROMPT, tool=contract.TOOL_SPEC)
    total, calls = Usage(), []
    for turn in range(1, max_turns + 1):
        resp = _create(client, body)
        total.add(_usage(resp))
        pending = [i for i in resp.output if i.type == "function_call"]
        if not pending:
            return _outcome(resp, model, total, turn, calls)
        # stateless: send back everything the model produced (reasoning items included), then the results
        body["input"] = list(body["input"]) + [i.model_dump(mode="json", exclude_none=True) for i in resp.output]
        for call in pending:
            calls.append(call.name)
            try:
                result = json.dumps(contract.get_vendor_renewals(data, **json.loads(call.arguments)))
            except (ValueError, TypeError) as exc:
                result = json.dumps({"error": str(exc)})
            body["input"].append({"type": "function_call_output", "call_id": call.call_id, "output": result})
    return Outcome("openai", model, "failed", usage=total, requests=max_turns, tool_calls=calls,
                   problems=[f"no final answer after {max_turns} turns"])
