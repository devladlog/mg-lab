"""python -m invoicekit preflight FILE...   |   python -m invoicekit triage FILE.json... [options]

preflight  exit 0 when every file meets Learn's limits, 1 when one doesn't. A PDF with several invoices
           also prints the Pages value for each (Learn: one invoice per range).
triage     reads extractions (the staging-list columns, see triage.py) and prints the decision and the reasons;
           exit 0 when every decision is auto-post, 1 otherwise. --known takes a JSON list of
           {"VendorName": ..., "InvoiceId": ...} already posted.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import preflight, triage


def cmd_preflight(a) -> int:
    bad = 0
    for f in a.files:
        findings = preflight.check_file(f)
        errors = [x for x in findings if x.level == "error"]
        bad += bool(errors)
        if not findings:
            print(f"OK       {Path(f).name}")
        for x in findings:
            print(f"{x.level.upper():8} {x.code} {x.text}")
        if not errors and str(f).lower().endswith(".pdf"):
            parts = preflight.split_invoices(f)
            if len(parts) > 1:
                print(f"         {len(parts)} invoices in one file, one flow run each:")
                for inv, pages in parts:
                    print(f"           Pages = {pages:<5} {inv}")
    return 1 if bad else 0


def cmd_triage(a) -> int:
    cfg = triage.Config(min_confidence=a.min_confidence, amount_limit=a.amount_limit)
    today = date.fromisoformat(a.today) if a.today else date.today()
    known = set()
    if a.known:
        known = {triage.dup_key(r.get("VendorName"), r.get("InvoiceId")) for r in json.loads(Path(a.known).read_text("utf-8"))}
    worst = 0
    for f in a.files:
        data = json.loads(Path(f).read_text("utf-8"))
        d = triage.decide(data, cfg, today, known)
        print(f"{d.action.upper():10} {Path(f).name}")
        for r in d.reasons:
            print(f"           {r.code}: {r.text}")
        worst |= d.action != triage.AUTO
    return int(worst)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="invoicekit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight", help="check files against the model's limits")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_preflight)
    t = sub.add_parser("triage", help="auto-post, review or reject extractions")
    t.add_argument("files", nargs="+")
    t.add_argument("--min-confidence", type=float, default=triage.Config.min_confidence)
    t.add_argument("--amount-limit", type=float, default=triage.Config.amount_limit)
    t.add_argument("--known", help="JSON list of invoices already posted")
    t.add_argument("--today", help="YYYY-MM-DD, for repeatable output")
    t.set_defaults(fn=cmd_triage)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
