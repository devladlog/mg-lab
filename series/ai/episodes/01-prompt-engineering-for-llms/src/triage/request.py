"""Build the Chat Completions request body for a deployment, respecting what the model family supports.

Microsoft Learn ("Azure OpenAI reasoning models"): reasoning models don't support temperature, top_p,
presence_penalty, frequency_penalty, logprobs, top_logprobs, logit_bias or max_tokens; with Chat Completions they
need max_completion_tokens, and reasoning tokens count toward that limit. The GPT-5 family and the o-series are
reasoning models. Check the model card for anything else.
"""
from __future__ import annotations

from typing import Any

from .prompts import Prompt

REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def is_reasoning_model(model: str) -> bool:
    return model.lower().startswith(REASONING_PREFIXES)


def build_request(
    prompt: Prompt,
    ticket: str,
    *,
    deployment: str,
    model: str,
    reasoning_effort: str = "low",
    max_output_tokens: int = 2000,
) -> dict[str, Any]:
    """Return kwargs for `client.chat.completions.create(**kwargs)`.

    `deployment` goes in `model` (Azure routes by deployment name); `model` is the underlying model name and only
    decides which sampling parameters are allowed.
    """
    body: dict[str, Any] = {"model": deployment, "messages": prompt.build_messages(ticket)}
    if prompt.response_format is not None:
        body["response_format"] = prompt.response_format
    if is_reasoning_model(model):
        body["reasoning_effort"] = reasoning_effort
        body["max_completion_tokens"] = max_output_tokens
    else:
        body["temperature"] = 0
        body["max_tokens"] = max_output_tokens
    return body
