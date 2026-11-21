#!/usr/bin/env python3
"""Compares an exported PDF of the store statement with the contract (contract/store-statement-2025.json).

  python3 verify_pdf.py statement-2025.pdf [--contract ../contract/store-statement-2025.json]

Checks, per page: the title, the store name (one store per page, in order), "Page n of N" and one text line per month with
Month, Sales Amount, Units and Margin % in that order. Also: the page count (a blank page after every page would double it).
Text comes from pdfplumber. Exit code 1 when something differs. Needs a real export to mean anything; the tests use a simulated one.
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

DEFAULT = Path(__file__).resolve().parent.parent / "contract" / "store-statement-2025.json"


def page_texts(pdf_path):
    with pdfplumber.open(str(pdf_path)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def verify(pdf_path, contract):
    problems = []
    texts = page_texts(pdf_path)
    n = contract["pages"]
    if len(texts) != n:
        blank = sum(1 for t in texts if not t.strip().replace(contract["title"], "").strip())
        problems.append(f"{len(texts)} pages, expected {n}" + (f" ({blank} look blank: body wider than the page?)" if blank else ""))
    for i, (store, text) in enumerate(zip(contract["stores"], texts), start=1):
        who = f"page {i} ({store['store']})"
        if contract["title"] not in text:
            problems.append(f"{who}: title '{contract['title']}' missing")
        if store["store"] not in text:
            problems.append(f"{who}: store name missing")
        others = [s["store"] for s in contract["stores"] if s["store"] != store["store"] and s["store"] in text]
        if others:
            problems.append(f"{who}: also shows {', '.join(others)}")
        if not re.search(rf"Page {i} of {len(texts)}\b", text):
            problems.append(f"{who}: footer 'Page {i} of {len(texts)}' missing")
        for m in store["months"]:
            pattern = r"\s+".join(re.escape(m[k]) for k in ("month", "sales_amount", "units", "margin_pct"))
            if not re.search(rf"^{pattern}\s*$", text, re.M):
                problems.append(f"{who}: row {m['month']} {m['sales_amount']} {m['units']} {m['margin_pct']} not found")
    return problems


def main(argv):
    if not argv or argv[0].startswith("-"):
        print("usage: verify_pdf.py <file.pdf> [--contract <json>]", file=sys.stderr)
        return 2
    contract = json.loads(Path(argv[argv.index("--contract") + 1] if "--contract" in argv else DEFAULT).read_text(encoding="utf-8"))
    problems = verify(argv[0], contract)
    for p in problems:
        print("MISMATCH", p)
    print("OK: the PDF matches the contract" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
