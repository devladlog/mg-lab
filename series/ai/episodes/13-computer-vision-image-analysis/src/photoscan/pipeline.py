"""One photo in, one safe result out. The original bytes are never written anywhere; only the pixelated copy and the
thumbnail are."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import assettag, decide, privacy
from .limits import ImageRejected
from .model import Analysis, VisionBackend
from .prepare import prepare


@dataclass
class Result:
    id: str
    decision: str = "manual-review"
    reasons: list[str] = field(default_factory=list)
    analysis: Analysis | None = None
    tags: list[assettag.TagRead] = field(default_factory=list)
    redacted_png: bytes | None = None
    thumb_png: bytes | None = None
    blurred: list = field(default_factory=list)
    ignored_people: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    prepared_png: bytes | None = None     # kept in memory for the evaluation, never written to disk


def process(raw: bytes, backend: VisionBackend, photo_id: str, person_threshold: float = privacy.PERSON_THRESHOLD) -> Result:
    r = Result(photo_id)
    try:
        prep = prepare(raw, photo_id)
    except ImageRejected as e:
        r.error = str(e)
        r.decision, r.reasons = decide.decide(None, [], r.error)
        return r
    r.notes, r.prepared_png = prep.notes, prep.data
    try:
        a = backend.analyze(prep.data)
    except Exception as e:                      # one bad call must not stop a batch; the photo goes to a person
        r.error = f"analysis failed: {type(e).__name__}: {e}"[:300]
        r.decision, r.reasons = decide.decide(None, [], r.error)
        return r
    r.analysis = a
    r.tags = assettag.find_tags(a.lines)
    red = privacy.redact_people(prep.data, a.people, person_threshold)
    r.redacted_png, r.blurred, r.ignored_people = red.data, red.blurred, red.ignored
    if a.crops:
        r.thumb_png = privacy.thumbnail(red.data, a.crops[0])
    r.decision, r.reasons = decide.decide(a, r.tags)
    return r


def write(r: Result, out: Path) -> dict:
    """Write the redacted image, the thumbnail and a JSON summary. Returns the summary."""
    out.mkdir(parents=True, exist_ok=True)
    safe = hashlib.sha256(r.id.encode()).hexdigest()[:10]
    if r.redacted_png:
        (out / f"{r.id}.redacted.png").write_bytes(r.redacted_png)
    if r.thumb_png:
        (out / f"{r.id}.thumb.png").write_bytes(r.thumb_png)
    a = r.analysis
    summary = {"id": r.id, "key": safe, "decision": r.decision, "reasons": r.reasons, "notes": r.notes, "error": r.error,
               "caption": a.caption if a else None, "tags": [n for n, _ in (a.tags[:8] if a else [])],
               "asset_tags": [t.tag for t in r.tags], "people_blurred": len(r.blurred), "people_below_threshold": r.ignored_people,
               "model_version": a.model_version if a else None}
    (out / f"{r.id}.json").write_text(json.dumps(summary, indent=2))
    return summary


class Paced:
    """Keep under the free tier's 20 calls per minute (Learn FAQ) by spacing calls. The SDK retries 429 as well."""
    def __init__(self, inner: VisionBackend, calls_per_minute: int = 20, clock=time.monotonic, sleep=time.sleep):
        self.inner, self.gap, self.clock, self.sleep, self.last = inner, 60.0 / calls_per_minute, clock, sleep, None

    def analyze(self, image: bytes) -> Analysis:
        if self.last is not None:
            wait = self.gap - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        self.last = self.clock()
        return self.inner.analyze(image)
