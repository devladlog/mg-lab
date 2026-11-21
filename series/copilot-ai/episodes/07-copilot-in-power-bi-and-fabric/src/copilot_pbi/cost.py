"""Copilot in Fabric capacity estimate, from the consumption rates published on Microsoft Learn.

Learn (Consumption rates and billing for Copilot in Fabric), per 1,000 tokens:
  input prompt 100 CU seconds, cached input prompt 10 CU seconds, output completion 400 CU seconds.
Copilot requests are background operations smoothed over 24 hours. Copilot itself has no per-user licence: it
consumes the CUs of the capacity, and a pay-as-you-go F SKU is billed per second while it runs, used or not.
Rates can change; the CLI prints the date they were checked.
"""
from __future__ import annotations

from dataclasses import dataclass

RATE_INPUT = 100.0   # CU seconds per 1,000 input tokens
RATE_CACHED = 10.0   # CU seconds per 1,000 cached input tokens
RATE_OUTPUT = 400.0  # CU seconds per 1,000 output tokens
RATES_CHECKED = "2026-11-21"

# CUs per SKU. F SKUs by name; P1..P5 map to F64..F1024 (Learn: Power BI Premium to Fabric migration)
SKU_CU = {
    "F2": 2, "F4": 4, "F8": 8, "F16": 16, "F32": 32, "F64": 64, "F128": 128, "F256": 256,
    "F512": 512, "F1024": 1024, "F2048": 2048,
    "P1": 64, "P2": 128, "P3": 256, "P4": 512, "P5": 1024,
}


@dataclass
class Estimate:
    sku: str
    cu: int
    cu_seconds_per_prompt: float
    prompts_per_day: int
    cu_seconds_per_day: float
    share_of_daily_capacity: float
    prompts_per_day_to_exhaust: float
    capacity_cost_per_hour: float | None
    window_hours: float | None
    window_cost: float | None


def cu_seconds_per_prompt(input_tokens: int, output_tokens: int, cached_share: float = 0.0) -> float:
    if not 0 <= cached_share <= 1:
        raise ValueError("cached_share must be between 0 and 1")
    fresh = input_tokens * (1 - cached_share)
    cached = input_tokens * cached_share
    return (fresh * RATE_INPUT + cached * RATE_CACHED + output_tokens * RATE_OUTPUT) / 1000.0


def estimate(sku: str, prompts_per_day: int, input_tokens: int, output_tokens: int, cached_share: float = 0.0,
             price_per_cu_hour: float | None = None, window_hours: float | None = None) -> Estimate:
    key = sku.upper()
    if key not in SKU_CU:
        raise ValueError(f"unknown SKU {sku!r}; known: {', '.join(SKU_CU)}")
    cu = SKU_CU[key]
    per = cu_seconds_per_prompt(input_tokens, output_tokens, cached_share)
    day_total = per * prompts_per_day
    capacity_day = cu * 86400.0
    cost_hour = cu * price_per_cu_hour if price_per_cu_hour is not None else None
    return Estimate(
        sku=key, cu=cu, cu_seconds_per_prompt=per, prompts_per_day=prompts_per_day,
        cu_seconds_per_day=day_total,
        share_of_daily_capacity=day_total / capacity_day,
        prompts_per_day_to_exhaust=(capacity_day / per) if per else float("inf"),
        capacity_cost_per_hour=cost_hour,
        window_hours=window_hours,
        window_cost=(cost_hour * window_hours) if (cost_hour is not None and window_hours is not None) else None,
    )
