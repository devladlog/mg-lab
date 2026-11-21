"""Thin, batched wrapper over the five preconfigured features we use. Results are plain dataclasses; a failed document
comes back as an Err for that id, it never raises for the whole batch."""
from __future__ import annotations

from dataclasses import dataclass, field

from azure.ai.textanalytics import DetectLanguageInput, TextDocumentInput

from .limits import MAX_CHARS, MAX_DOCS, batched


@dataclass
class Err:
    code: str
    message: str


@dataclass
class Lang:
    iso: str
    name: str
    confidence: float


@dataclass
class Sent:
    label: str                                   # positive | neutral | negative | mixed
    scores: dict[str, float]
    aspects: list[tuple[str, str]] = field(default_factory=list)   # (target text, sentiment of the target)


@dataclass
class Pii:
    redacted: str
    categories: list[str]


@dataclass
class Ent:
    text: str
    category: str


class Analyzer:
    def __init__(self, client):
        self.client = client
        self.calls: dict[str, int] = {}              # requests per feature (for the report)

    def _count(self, feature: str):
        self.calls[feature] = self.calls.get(feature, 0) + 1

    def _run(self, feature: str, call, items: list[tuple[str, str, str | None]], convert, **kw) -> dict:
        """items = (id, text, language). Batches by the documented limit; every id gets a value or an Err."""
        out: dict = {}
        for batch in batched(items, MAX_DOCS[feature]):
            docs = []
            for i, text, lang in batch:
                if len(text) > MAX_CHARS:
                    out[i] = Err("DocumentTooLong", f"{len(text)} characters, limit {MAX_CHARS}: split it first")
                elif feature == "language":
                    docs.append(DetectLanguageInput(id=i, text=text))
                else:
                    docs.append(TextDocumentInput(id=i, text=text, language=lang))
            if not docs:
                continue
            self._count(feature)
            for r in call(docs, **kw):
                out[r.id] = Err(r.error.code, r.error.message) if r.is_error else convert(r)
        for i, _, _ in items:
            out.setdefault(i, Err("NoResult", "the service returned nothing for this document"))
        return out

    def languages(self, items):
        return self._run("language", self.client.detect_language, items,
                         lambda r: Lang(r.primary_language.iso6391_name, r.primary_language.name, r.primary_language.confidence_score))

    def pii(self, items):
        return self._run("pii", self.client.recognize_pii_entities, items,
                         lambda r: Pii(r.redacted_text, [e.category for e in r.entities]))

    def sentiment(self, items):
        def conv(r):
            aspects = [(op.target.text, op.target.sentiment) for s in r.sentences for op in (s.mined_opinions or [])]
            c = r.confidence_scores
            return Sent(r.sentiment, {"positive": c.positive, "neutral": c.neutral, "negative": c.negative}, aspects)
        return self._run("sentiment", self.client.analyze_sentiment, items, conv, show_opinion_mining=True)

    def key_phrases(self, items):
        return self._run("key_phrases", self.client.extract_key_phrases, items, lambda r: list(r.key_phrases))

    def entities(self, items):
        return self._run("entities", self.client.recognize_entities, items,
                         lambda r: [Ent(e.text, e.category) for e in r.entities])
