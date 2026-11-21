"""A Markdown report over many analysed tickets: no ticket text, only redacted-derived aggregates."""
from __future__ import annotations

from collections import Counter

from .pipeline import Analysis
from .route import route

GENERIC = {"ticket", "tickets", "problem", "issue", "help", "team", "please", "thanks", "thank you"}


def build_report(analyses: list[Analysis], calls: dict[str, int] | None = None, records: dict[str, int] | None = None) -> str:
    n = len(analyses)
    langs = Counter(a.language or "none" for a in analyses)
    sents = Counter(a.sentiment or "none" for a in analyses)
    queues = Counter(route(a)[0] for a in analyses)
    pii = Counter()
    for a in analyses:
        pii.update(a.pii_categories)
        pii.update({h: 1 for h in a.backstop_hits})
    phrases = Counter(p.lower() for a in analyses if a.sentiment == "negative" for p in a.key_phrases if p.lower() not in GENERIC)
    aspects = Counter(t.lower() for a in analyses for t, s in a.aspects if s == "negative")

    def table(title, c):
        rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))) or "| - | 0 |"
        return f"### {title}\n\n| value | tickets |\n|---|---|\n{rows}\n"

    out = [f"# Ticket analysis: {n} tickets\n", table("Language", langs), table("Sentiment", sents), table("Next step", queues),
           table("PII removed before analysis (by category)", pii),
           table("Top key phrases in negative tickets", Counter(dict(phrases.most_common(8)))),
           table("Top negative aspects (opinion mining)", Counter(dict(aspects.most_common(8))))]
    skipped = [a.id for a in analyses if a.skipped or a.errors]
    out.append(f"### Not analysed or partly failed\n\n{', '.join(skipped) if skipped else 'none'}\n")
    if calls:
        out.append("### Requests sent\n\n" + ", ".join(f"{k}: {v}" for k, v in sorted(calls.items())) + "\n")
    if records:
        out.append("### Text records (estimate, worst case)\n\n" + ", ".join(f"{k}: {v}" for k, v in records.items()) + "\n")
    return "\n".join(out)
