"""Run the labelled cases through the pipeline and score it. The hard gate is privacy: no labelled PII string may survive in
anything the pipeline outputs (redacted text, key phrases, entities, aspects). Accuracy gates are deliberately modest:
the labels are ours, the set is small, and sentiment on short tickets is a judgement call."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import Analyzer
from .pipeline import Analysis, process

CASES_FILE = Path(__file__).resolve().parents[2] / "data" / "tickets.json"
MIN_LANGUAGE_ACCURACY = 0.90
MIN_SENTIMENT_ACCURACY = 0.75


def load_cases(path=None) -> list[dict]:
    cases = json.loads(Path(path or CASES_FILE).read_text(encoding="utf-8"))
    for c in cases:
        if c.get("text") is None:
            r = c["text_repeat"]
            c["text"] = r["head"] + r["unit"] * r["times"]
    return cases


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def leaked(a: Analysis, pii: list[str]) -> list[str]:
    """Which labelled PII strings still appear in anything the pipeline produced for this ticket."""
    haystack = [a.redacted_text, *a.key_phrases, *(t for t, _ in a.entities), *(t for t, _ in a.aspects)]
    flat = _norm(" ".join(haystack))
    flat_digits = _digits(" ".join(haystack))
    found = []
    for p in pii:
        if _norm(p) in flat or (len(_digits(p)) >= 7 and _digits(p) in flat_digits):
            found.append(p)
    return found


@dataclass
class Score:
    mode: str
    cases: int = 0
    language_ok: int = 0
    language_n: int = 0
    sentiment_ok: int = 0
    sentiment_n: int = 0
    leaks: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)      # errors, skips: always gated
    mismatches: list[str] = field(default_factory=list)    # wrong language or sentiment: gated through the accuracy only
    requests: dict[str, int] = field(default_factory=dict)

    @property
    def language_acc(self):
        return self.language_ok / self.language_n if self.language_n else 1.0

    @property
    def sentiment_acc(self):
        return self.sentiment_ok / self.sentiment_n if self.sentiment_n else 1.0


def score(analyzer_factory, cases: list[dict], redact: bool = True) -> tuple[Score, list[Analysis]]:
    an = analyzer_factory()
    results = process(an, [(c["id"], c["text"]) for c in cases], redact=redact)
    s = Score("redact first" if redact else "analyse raw text", cases=len(cases), requests=dict(an.calls))
    for c, a in zip(cases, results):
        if c.get("expect_skip"):
            if not a.skipped:
                s.problems.append(f"{c['id']}: expected to be skipped")
            continue
        if a.skipped or a.errors:
            s.problems.append(f"{c['id']}: {a.skipped or '; '.join(a.errors)}")
        if c.get("language"):
            s.language_n += 1
            s.language_ok += int((a.language or "")[:2] == c["language"])
            if (a.language or "")[:2] != c["language"]:
                s.mismatches.append(f"{c['id']}: language {a.language!r}, expected {c['language']!r}")
        if c.get("sentiment"):
            s.sentiment_n += 1
            s.sentiment_ok += int(a.sentiment == c["sentiment"])
            if a.sentiment != c["sentiment"]:
                s.mismatches.append(f"{c['id']}: sentiment {a.sentiment!r}, expected {c['sentiment']!r}")
        s.leaks += [f"{c['id']}: {p}" for p in leaked(a, c.get("pii", []))]
    return s, results


def gate(s: Score) -> tuple[bool, list[str]]:
    why = []
    if s.leaks:
        why.append(f"{len(s.leaks)} labelled PII string(s) survived: " + "; ".join(s.leaks))
    if s.language_acc < MIN_LANGUAGE_ACCURACY:
        why.append(f"language accuracy {s.language_acc:.0%} < {MIN_LANGUAGE_ACCURACY:.0%}")
    if s.sentiment_acc < MIN_SENTIMENT_ACCURACY:
        why.append(f"sentiment accuracy {s.sentiment_acc:.0%} < {MIN_SENTIMENT_ACCURACY:.0%}")
    if s.problems:
        why.append("unexpected errors or skips: " + "; ".join(s.problems))
    return not why, why


def format_report(scores: list[Score]) -> str:
    rows = ["mode                 cases  language  sentiment  PII leaks  requests", "-" * 72]
    for s in scores:
        req = ", ".join(f"{k}={v}" for k, v in sorted(s.requests.items()))
        rows.append(f"{s.mode:<20} {s.cases:>5}  {s.language_ok:>2}/{s.language_n:<2} {s.language_acc:>4.0%}  "
                    f"{s.sentiment_ok:>2}/{s.sentiment_n:<2} {s.sentiment_acc:>4.0%}  {len(s.leaks):>9}  {req}")
    for s in scores:
        for p in s.problems + s.mismatches:
            rows.append(f"  [{s.mode}] {p}")
        for leak in s.leaks:
            rows.append(f"  [{s.mode}] LEAK {leak}")
    ok, why = gate(scores[0])
    rows.append("")
    rows.append(f"RESULT ({scores[0].mode}): " + ("PASS" if ok else "FAIL - " + " | ".join(why)))
    return "\n".join(rows)
