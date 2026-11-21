"""Next step for a photo, as plain rules with reasons. Every threshold is ours; tune it on your own photos."""
from __future__ import annotations

from .assettag import TagRead, usable
from .model import Analysis


def decide(a: Analysis | None, tags: list[TagRead], error: str | None = None) -> tuple[str, list[str]]:
    if error or a is None:
        return "manual-review", [error or "no analysis"]
    reasons: list[str] = []
    if a.people and a.lines:
        reasons.append("text is visible in a photo with people: names on badges or screens are not blurred")
    distinct = {t.tag for t in tags}
    if len(distinct) > 1:
        return "manual-review", reasons + [f"{len(distinct)} different asset tags in one photo"]
    if not tags:
        return "manual-review", reasons + ["no asset tag read"]
    t = tags[0]
    if t.corrected:
        return "confirm-tag", reasons + [f"printed {t.raw!r} read as {t.tag}: look-alike letters replaced"]
    if not usable(t):
        return "manual-review", reasons + [f"{t.tag} read with confidence {t.confidence:.2f} (< 0.80)"]
    if reasons:
        return "attach-then-review", reasons
    return "attach-to-asset", [f"{t.tag} read with confidence {t.confidence:.2f}"]
