"""The context window is a budget shared by everything: system message, retrieved text, history, the question, and the
answer you allow. Learn: input, output and reasoning tokens share the budget; max output tokens is an upper limit,
not a reservation. gpt-4.1-mini: 1,047,576-token context window, 300,000 on Standard deployments, 32,768 max output."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .tokens import count

MODEL_CONTEXT = 1_047_576
STANDARD_CONTEXT = 300_000
MAX_OUTPUT = 32_768


class BudgetError(ValueError):
    pass


@dataclass(frozen=True)
class Plan:
    window: int
    reserve_output: int
    fixed_tokens: int       # system message + question (+ anything else that is always sent)
    available: int          # what is left for retrieved text and history


def make_plan(window: int, reserve_output: int, fixed_tokens: int) -> Plan:
    if reserve_output > MAX_OUTPUT:
        raise BudgetError(f"max output is {MAX_OUTPUT:,} tokens for gpt-4.1-mini (Learn); asked for {reserve_output:,}")
    if window > MODEL_CONTEXT:
        raise BudgetError(f"the model's context window is {MODEL_CONTEXT:,} tokens; asked for {window:,}")
    left = window - reserve_output - fixed_tokens
    if left < 0:
        raise BudgetError(f"system message and question ({fixed_tokens:,}) plus the answer you reserve ({reserve_output:,}) "
                          f"do not fit in {window:,} tokens")
    return Plan(window, reserve_output, fixed_tokens, left)


def split_sections(markdown: str) -> list[str]:
    """One chunk per '## ' section; the leading title and HTML comments are dropped."""
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.S)
    parts = re.split(r"(?m)^(?=## )", text)
    return [p.strip() for p in parts if p.strip().startswith("## ")]


def fit_chunks(chunks: list[str], budget: int, encoding: str = "o200k_base") -> tuple[list[str], list[str]]:
    """Keep chunks in rank order until the next one does not fit, then stop: dropping a high-ranked chunk
    and keeping a lower-ranked one would silently reorder relevance."""
    kept, used = [], 0
    for i, c in enumerate(chunks):
        n = count(c, encoding)
        if used + n > budget:
            return kept, chunks[i:]
        kept.append(c)
        used += n
    return kept, []


def check_request(window: int, prompt_tokens: int, max_completion: int) -> None:
    if max_completion > MAX_OUTPUT:
        raise BudgetError(f"max_completion_tokens {max_completion:,} is above the model's maximum output of {MAX_OUTPUT:,}")
    if prompt_tokens + max_completion > window:
        raise BudgetError(f"{prompt_tokens:,} prompt + {max_completion:,} output tokens exceed the {window:,}-token window")


def content_tokens(messages: list[dict], encoding: str = "o200k_base") -> int:
    """Tokens of the message texts only. The service bills a little more (chat format); the CLI prints the real difference."""
    return sum(count(m["content"], encoding) for m in messages)
