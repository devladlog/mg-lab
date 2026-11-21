"""The plain-Python reference for the KQL queries: what the Eventhouse should answer for the events of one run.

It is not a copy of ``series_decompose_anomalies``. It answers the simpler question "which minutes are far above the rest",
with a median and the median absolute deviation, so you can see whether the KQL anomaly query points at the same minutes.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def read_ndjson(path: Path | str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def dedupe(records: list[dict]) -> list[dict]:
    """One record per EventId (the first seen), like ``summarize take_any(*) by EventId``."""
    seen: dict[str, dict] = {}
    for r in records:
        seen.setdefault(r["EventId"], r)
    return list(seen.values())


def totals(records: list[dict]) -> dict:
    """Same numbers as totals-check.kql: events, units, amount, and what the duplicates added to the raw table."""
    unique = dedupe(records)
    return {"raw_rows": len(records), "events": len(unique), "duplicate_rows": len(records) - len(unique),
            "units": sum(r["Quantity"] for r in unique), "amount": round(sum(r["Amount"] for r in unique), 2),
            "amount_raw": round(sum(r["Amount"] for r in records), 2)}


def minute_of(r: dict) -> str:
    return r["EventTime"][:16] + ":00Z"  # bin(EventTime, 1m)


def per_minute(records: list[dict], channel: str | None = None, measure: str = "orders") -> dict[str, float]:
    """Orders (count of unique events) or amount per minute, like ``summarize count() by bin(EventTime, 1m)``."""
    if measure not in ("orders", "amount"):
        raise ValueError("measure must be 'orders' or 'amount'")
    out: dict[str, float] = defaultdict(float)
    for r in dedupe(records):
        if channel is None or r["Channel"] == channel:
            out[minute_of(r)] += 1 if measure == "orders" else r["Amount"]
    return {k: round(v, 2) for k, v in sorted(out.items())}


def spike_minutes(series: dict[str, float], k: float = 3.5) -> list[str]:
    """Minutes whose value is more than ``k`` robust standard deviations above the median (0.6745 * |x - median| / MAD)."""
    values = list(series.values())
    if len(values) < 4:
        return []
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values)
    if mad == 0:
        return [m for m, v in series.items() if v > med]
    return [m for m, v in series.items() if 0.6745 * (v - med) / mad > k]

