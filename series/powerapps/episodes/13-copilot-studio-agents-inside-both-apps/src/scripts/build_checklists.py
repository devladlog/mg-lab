#!/usr/bin/env python3
"""Build the three Word checklists for the SharePoint library from src/checklists/checklists.json (so no binary files live in the repo).

  python build_checklists.py --out /tmp/checklists        # needs: pip install python-docx
"""
import argparse
import json
from pathlib import Path

import docx

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "checklists" / "checklists.json"


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    for name, c in data.items():
        d = docx.Document()
        d.add_heading(c["title"], level=1)
        d.add_paragraph(c["intro"])
        for item in c["items"]:
            d.add_paragraph(item, style="List Number")
        d.save(out / name)
    return sorted(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    print("\n".join(build(ap.parse_args().out)))
