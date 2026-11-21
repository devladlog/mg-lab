"""Which parameters a model family accepts. Learn: reasoning models do not support temperature, top_p, the penalties,
logprobs, top_logprobs, logit_bias or max_tokens, so every experiment in this package needs a non-reasoning model."""
from __future__ import annotations

import re

_REASONING = re.compile(r"^(o\d|gpt-5)")


class ModelError(ValueError):
    pass


def is_reasoning_family(model: str) -> bool:
    return bool(_REASONING.match(model.strip().lower()))


def ensure_sampling_model(model: str, allow_unverified: bool = False) -> None:
    """Refuse a model name that belongs to a family where temperature / logprobs are documented as unsupported."""
    if is_reasoning_family(model) and not allow_unverified:
        raise ModelError(
            f"{model!r} looks like a reasoning-family model: Learn lists temperature, top_p, logprobs and "
            "top_logprobs as unsupported there. Use a non-reasoning deployment such as gpt-4.1-mini, or pass "
            "--allow-unverified-model if you have checked that this model accepts them."
        )
