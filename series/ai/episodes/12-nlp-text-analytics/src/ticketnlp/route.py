"""What happens to a ticket next. Plain rules over the analysis, in a fixed order, each with a stated reason."""
from __future__ import annotations

from .pipeline import Analysis

HANDLED_LANGUAGES = ("en", "pt")
NEGATIVE_ESCALATION = 0.85


def route(a: Analysis) -> tuple[str, list[str]]:
    if a.skipped or a.errors:
        return "manual-review", [a.skipped or "; ".join(a.errors)]
    if a.language_uncertain:
        return "manual-review", [f"language uncertain ({a.language}, {a.language_confidence:.2f})"]
    if a.language not in HANDLED_LANGUAGES:
        return "translate-first", [f"language {a.language} has no support queue"]
    neg = a.sentiment_scores.get("negative", 0.0)
    if a.sentiment == "negative" and neg >= NEGATIVE_ESCALATION:
        return "priority-review", [f"negative {neg:.2f} >= {NEGATIVE_ESCALATION}"]
    if a.sentiment == "positive":
        return "feedback-log", ["positive"]
    return "standard", [a.sentiment or "no sentiment"]
