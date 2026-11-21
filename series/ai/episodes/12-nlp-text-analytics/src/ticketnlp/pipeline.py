"""Ticket text in, analysis out. Order matters: language -> PII redaction -> local backstop -> analytics on the REDACTED
text. If redaction fails for a ticket, nothing else runs on its raw text (fail closed)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import backstop
from .analyzer import Analyzer, Err
from .limits import MAX_CHARS, split_text

MIN_LANGUAGE_CONFIDENCE = 0.6


@dataclass
class Analysis:
    id: str
    chunks: int = 0
    language: str | None = None
    language_confidence: float | None = None
    language_uncertain: bool = False
    redacted_text: str = ""
    pii_categories: dict[str, int] = field(default_factory=dict)
    backstop_hits: list[str] = field(default_factory=list)
    sentiment: str | None = None
    sentiment_scores: dict[str, float] = field(default_factory=dict)
    aspects: list[tuple[str, str]] = field(default_factory=list)
    key_phrases: list[str] = field(default_factory=list)
    entities: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: str | None = None


def merge_sentiment(parts: list[tuple[int, str, dict[str, float]]]) -> tuple[str, dict[str, float]]:
    """parts = (chunk length, label, scores). Our rule, not the service's: scores are length-weighted means; the label is
    the shared label if all chunks agree, otherwise 'mixed'."""
    total = sum(n for n, _, _ in parts) or 1
    scores = {k: sum(n * s[k] for n, _, s in parts) / total for k in ("positive", "neutral", "negative")}
    labels = {lab for _, lab, _ in parts}
    return (labels.pop() if len(labels) == 1 else "mixed"), scores


def process(an: Analyzer, records: list[tuple[str, str]], redact: bool = True) -> list[Analysis]:
    """records = (id, text). Returns one Analysis per record, in order. redact=False analyses the RAW text: it exists only so
    the evaluation can show what that leaks; do not ship it."""
    results = {rid: Analysis(rid) for rid, _ in records}
    chunks: dict[str, list[str]] = {}
    for rid, text in records:
        parts = split_text(text or "", MAX_CHARS)
        if not parts:
            results[rid].skipped = "empty text"
            continue
        chunks[rid] = parts
        results[rid].chunks = len(parts)

    # 1. language, from the first chunk
    langs = an.languages([(rid, c[0], None) for rid, c in chunks.items()])
    code: dict[str, str | None] = {}
    for rid in chunks:
        v = langs[rid]
        if isinstance(v, Err):
            results[rid].errors.append(f"language: {v.code}")
            code[rid] = None
            continue
        results[rid].language, results[rid].language_confidence = v.iso, v.confidence
        results[rid].language_uncertain = v.confidence < MIN_LANGUAGE_CONFIDENCE
        code[rid] = None if results[rid].language_uncertain else v.iso       # None: the service then assumes English

    # 2. PII on every chunk; failure blocks the ticket
    pii_in = [(f"{rid}#{i}", t, code[rid]) for rid, cs in chunks.items() for i, t in enumerate(cs)]
    pii = an.pii(pii_in) if redact else {}
    clean: dict[str, list[str]] = {}
    for rid, cs in chunks.items():
        out, cats, ok = [], Counter(), True
        for i in range(len(cs)):
            if not redact:
                out.append(cs[i])
                continue
            v = pii[f"{rid}#{i}"]
            if isinstance(v, Err):
                results[rid].errors.append(f"pii: {v.code}")
                ok = False
                break
            text, hits = backstop.redact(v.redacted)
            out.append(text)
            cats.update(v.categories)
            results[rid].backstop_hits += hits
        if ok:
            clean[rid] = out
            results[rid].redacted_text = "\n\n".join(out) if redact else ""     # raw text is never kept
            results[rid].pii_categories = dict(cats)
        else:
            results[rid].skipped = "blocked: PII redaction failed, raw text not analysed"

    # 3. analytics on the redacted chunks only
    items = [(f"{rid}#{i}", t, code[rid]) for rid, cs in clean.items() for i, t in enumerate(cs)]
    sent, kp, ents = an.sentiment(items), an.key_phrases(items), an.entities(items)
    for rid, cs in clean.items():
        a, parts, seen_kp, seen_ent = results[rid], [], set(), set()
        for i, t in enumerate(cs):
            k = f"{rid}#{i}"
            for name, res in (("sentiment", sent[k]), ("key_phrases", kp[k]), ("entities", ents[k])):
                if isinstance(res, Err):
                    a.errors.append(f"{name}: {res.code}")
            if not isinstance(sent[k], Err):
                parts.append((len(t), sent[k].label, sent[k].scores))
                a.aspects += sent[k].aspects
            if not isinstance(kp[k], Err):
                for p in kp[k]:
                    if p.lower() not in seen_kp:
                        seen_kp.add(p.lower())
                        a.key_phrases.append(p)
            if not isinstance(ents[k], Err):
                for e in ents[k]:
                    if (e.text.lower(), e.category) not in seen_ent:
                        seen_ent.add((e.text.lower(), e.category))
                        a.entities.append((e.text, e.category))
        if parts:
            a.sentiment, a.sentiment_scores = merge_sentiment(parts)
    return [results[rid] for rid, _ in records]
