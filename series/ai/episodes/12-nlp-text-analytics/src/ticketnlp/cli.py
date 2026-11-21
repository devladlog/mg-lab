"""python -m ticketnlp limits | show | analyze | evaluate"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import cost, evaluate as ev
from .analyzer import Analyzer
from .client import make_client
from .limits import F0_FREE_RECORDS_PER_MONTH, MAX_CHARS, MAX_DOCS, split_text
from .report import build_report


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ticketnlp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, h in (("analyze", "analyse the tickets in a JSON file and write a Markdown report"),
                    ("evaluate", "score the labelled cases; exit 1 if the privacy or accuracy gate fails"),
                    ("show", "analyse ONE ticket and print every step, original next to redacted"),
                    ("limits", "print the documented limits and the text-record estimate for a file (no Azure call)")):
        p = sub.add_parser(name, help=h)
        p.add_argument("--input", default=str(ev.CASES_FILE))
        if name != "limits":
            p.add_argument("--endpoint", default=os.environ.get("TICKETNLP_ENDPOINT"), help="https://<custom-subdomain>.cognitiveservices.azure.com")
        if name == "show":
            p.add_argument("--id", required=True, help="ticket id from the input file, e.g. en-neg-vpn")
        if name == "analyze":
            p.add_argument("--out", default="build/report.md")
            p.add_argument("--json", default=None, help="also write the per-ticket analysis (redacted) as JSON")
        if name == "evaluate":
            p.add_argument("--compare", action="store_true", help="also run on the raw text, to show what that leaks")
    return ap


def _factory(a):
    if not a.endpoint:
        raise SystemExit("--endpoint or TICKETNLP_ENDPOINT is required")
    client = make_client(a.endpoint)
    return lambda: Analyzer(client)


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        cases = ev.load_cases(a.input)
        if a.cmd == "limits":
            texts = [c["text"] for c in cases]
            est = cost.estimate(texts)
            print(f"documents per request: {MAX_DOCS}; characters per document: {MAX_CHARS}")
            print(f"{len(texts)} tickets -> {sum(len(split_text(t)) for t in texts)} chunks; longest ticket {max(len(t) for t in texts)} characters")
            print("estimated text records per run: " + ", ".join(f"{k}={v}" for k, v in est.items()))
            print(f"free tier: {F0_FREE_RECORDS_PER_MONTH} text records a month -> {cost.months_of_free_tier(est['total'], 1):.1%} of it per run")
            return 0
        if a.cmd == "show":
            from .pipeline import process
            from .route import route
            case = next((c for c in cases if c["id"] == a.id), None)
            if case is None:
                raise SystemExit(f"no ticket with id {a.id!r}; ids: {', '.join(c['id'] for c in cases)}")
            r = process(_factory(a)(), [(case["id"], case["text"])])[0]
            shown = case["text"] if len(case["text"]) <= 400 else case["text"][:400] + f"... ({len(case['text'])} characters)"
            print(f"original   : {shown}")
            print(f"language   : {r.language} ({(r.language_confidence or 0):.2f}){' UNCERTAIN' if r.language_uncertain else ''}")
            print(f"redacted   : {r.redacted_text[:400]}")
            print(f"PII removed: {r.pii_categories} backstop: {r.backstop_hits}")
            print(f"sentiment  : {r.sentiment} {({k: round(v, 2) for k, v in r.sentiment_scores.items()})}")
            print(f"aspects    : {r.aspects}")
            print(f"key phrases: {r.key_phrases}")
            print(f"entities   : {r.entities}")
            print(f"next step  : {route(r)}")
            return 0
        if a.cmd == "evaluate":
            f = _factory(a)
            runs = [ev.score(f, cases, redact=True)[0]] + ([ev.score(f, cases, redact=False)[0]] if a.compare else [])
            print(ev.format_report(runs))
            return 0 if ev.gate(runs[0])[0] else 1
        from .pipeline import process
        an = _factory(a)()
        results = process(an, [(c["id"], c["text"]) for c in cases])
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_report(results, an.calls, cost.estimate([c["text"] for c in cases])), encoding="utf-8")
        if a.json:
            Path(a.json).write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
        print(out.read_text(encoding="utf-8"))
        return 0
    except SystemExit:
        raise
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
