"""Client-side fallback across Claude deployments.

Anthropic's Claude-on-Foundry page lists the server-side `fallbacks` parameter as not supported on Foundry and says to
use a client-side pattern. This is that pattern: try the deployments in order and move on only for errors that another
deployment can fix (rate limit, server error, connection). A wrong deployment name (404) or a bad request (400) is a
bug in your configuration and is raised, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import anthropic


@dataclass
class FallbackResult:
    deployment: str
    text: str
    input_tokens: int
    output_tokens: int
    skipped: list = field(default_factory=list)  # [(deployment, reason)]


RETRYABLE = (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError)


def ask_with_fallback(
    client,
    deployments: Sequence[str],
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = 512,
) -> FallbackResult:
    if not deployments:
        raise ValueError("at least one deployment is required")
    one_shot = client.with_options(max_retries=0)  # we do the failing over, the SDK must not retry the same deployment
    skipped: list = []
    for dep in deployments:
        kwargs = {"model": dep, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        try:
            resp = one_shot.messages.create(**kwargs)
        except RETRYABLE as exc:
            skipped.append((dep, f"{type(exc).__name__}"))
            continue
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
        return FallbackResult(dep, text, resp.usage.input_tokens, resp.usage.output_tokens, skipped)
    raise RuntimeError("all deployments failed: " + ", ".join(f"{d}: {r}" for d, r in skipped))
