"""One result shape for both vendors, so a run can be compared line by line."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0      # OpenAI: includes reasoning tokens. Gemini: total_output_tokens, thought tokens are separate.
    reasoning_tokens: int = 0
    cached_tokens: int = 0

    def billable_output(self, vendor: str) -> int:
        """Both vendors bill thinking as output. OpenAI already includes it in output_tokens, Gemini reports it separately."""
        return self.output_tokens + (self.reasoning_tokens if vendor == "gemini" else 0)

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cached_tokens += other.cached_tokens


@dataclass
class Outcome:
    vendor: str
    model: str
    status: str                       # complete | truncated | refused | failed
    text: str = ""
    parsed: Optional[dict] = None
    usage: Usage = field(default_factory=Usage)
    tool_calls: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    requests: int = 1                 # round trips (a tool call costs a second one)

    @property
    def ok(self) -> bool:
        return self.status == "complete" and not self.problems


def load_prices(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def estimate_cost_usd(outcome: Outcome, prices: dict) -> Optional[float]:
    p = prices["models"].get(outcome.model)
    if p is None:
        return None
    u = outcome.usage
    fresh = max(u.input_tokens - u.cached_tokens, 0)
    out = u.billable_output(outcome.vendor)
    return (fresh * p["input"] + u.cached_tokens * p["cached_input"] + out * p["output"]) / 1_000_000
