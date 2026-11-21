"""Fine-tuning money, with no prices baked in.

Learn's cost page: SFT training price = training tokens x epochs x price per token; a deployed fine-tuned model also
has an hourly hosting fee (Standard / Global Standard) on top of per-token inference. Rates change and differ per
model and deployment type, so every price here is an argument: copy it from https://aka.ms/oai/pricing."""
from __future__ import annotations

from dataclasses import dataclass

HOURS_PER_MONTH = 730


def training_cost(training_tokens: int, epochs: int, price_per_million: float) -> float:
    return training_tokens * epochs / 1_000_000 * price_per_million


@dataclass(frozen=True)
class Serving:
    prompt_tokens: float          # input tokens per call
    completion_tokens: float      # output tokens per call
    input_per_million: float
    output_per_million: float
    hosting_per_hour: float = 0.0  # fine-tuned deployments only; Developer deployments have none (Learn)

    def per_call(self) -> float:
        return (self.prompt_tokens * self.input_per_million + self.completion_tokens * self.output_per_million) / 1e6

    def monthly(self, calls: float) -> float:
        return calls * self.per_call() + self.hosting_per_hour * HOURS_PER_MONTH


def breakeven_calls_per_month(base: Serving, tuned: Serving, training: float, amortise_months: int = 12) -> float | None:
    """Calls per month above which the tuned model is cheaper than the long-prompt baseline, counting the hosting
    fee and the training bill spread over `amortise_months`. None when the tuned model is not cheaper per call
    (then it never pays back on price, and must win on quality or latency instead)."""
    saving = base.per_call() - tuned.per_call()
    if saving <= 0:
        return None
    fixed = tuned.hosting_per_hour * HOURS_PER_MONTH + training / amortise_months
    return fixed / saving
