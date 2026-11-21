"""python -m copilot_chat_audit EXPORT.csv [--licensed users.txt] [--since 2026-11-01] [--json]"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .parse import load_records
from .summary import format_text, load_user_list, summarise


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilot_chat_audit", description=__doc__)
    p.add_argument("export", help="CSV from Export-CopilotInteractions.ps1 or the Purview portal, or a JSON/JSONL file")
    p.add_argument("--licensed", help="text file with the UPNs that hold the Microsoft 365 Copilot add-on")
    p.add_argument("--since", help="only interactions on or after this date (UTC, YYYY-MM-DD)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    result = load_records(args.export)
    licensed = load_user_list(Path(args.licensed).read_text(encoding="utf-8-sig")) if args.licensed else None
    since = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None
    summary = summarise(result.interactions, licensed=licensed, since=since)
    summary["skipped"] = {"otherOperations": result.skipped_other_operations, "unreadable": result.skipped_unreadable}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_text(summary))
        print(f"Skipped: {result.skipped_other_operations} other operation(s), {result.skipped_unreadable} unreadable row(s)")
    if not result.interactions:
        print("No CopilotInteraction records found.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
