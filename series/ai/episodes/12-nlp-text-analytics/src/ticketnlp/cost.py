"""Estimate of billed text records. Learn: pricing is per text record, a record is 1,000 characters, the free tier
covers 5,000 records a month. We sum the five features as a worst case: whether features are billed together is not
something this code assumes. Chunks are counted separately (each one is a document)."""
from __future__ import annotations

from .limits import F0_FREE_RECORDS_PER_MONTH, MAX_CHARS, split_text, text_records


def estimate(texts: list[str]) -> dict[str, int]:
    per = {"language": 0, "pii": 0, "sentiment": 0, "key_phrases": 0, "entities": 0}
    for t in texts:
        chunks = split_text(t or "", MAX_CHARS)
        if not chunks:
            continue
        per["language"] += text_records(chunks[0])
        rec = sum(text_records(c) for c in chunks)
        for k in ("pii", "sentiment", "key_phrases", "entities"):
            per[k] += rec
    per["total"] = sum(per.values())
    return per


def months_of_free_tier(total_per_run: int, runs_per_month: int) -> float:
    return (total_per_run * runs_per_month) / F0_FREE_RECORDS_PER_MONTH
