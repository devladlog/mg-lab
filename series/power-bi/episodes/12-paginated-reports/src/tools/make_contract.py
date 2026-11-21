#!/usr/bin/env python3
"""The contract of the export: what the PDF of the report must contain, from expected.py.

  python3 make_contract.py          # writes ../contract/store-statement-2025.json
  python3 make_contract.py --check  # fails when the committed contract is out of date
verify_pdf.py compares a real export (or the simulated one in the tests) with this file.
"""
import argparse
import json
import sys
from pathlib import Path

import expected

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "contract" / "store-statement-2025.json"
YEAR = 2025


def build() -> dict:
    rows = expected.statement_rows(YEAR)
    stores = []
    for name in sorted({r["store"] for r in rows}):
        months = [{k: r[k] for k in ("month", "sales_amount", "units", "margin_pct")} for r in rows if r["store"] == name]
        stores.append({"store": name, "months": months})
    return {
        "report": "ContosoStoreStatement", "year": YEAR, "format": "PDF",
        "title": f"Contoso Bikes store statement {YEAR}",
        "pages": len(stores),                       # one page per store: a store has 12 rows at most
        "page_footer": "Page {n} of {total}",
        "columns": ["Month", "Sales Amount", "Units", "Margin %"],
        "stores": stores,
    }


def render() -> str:
    return json.dumps(build(), indent=2) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = render()
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("contract is out of date, run tools/make_contract.py")
        print("up to date")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT} ({len(build()['stores'])} stores)")
