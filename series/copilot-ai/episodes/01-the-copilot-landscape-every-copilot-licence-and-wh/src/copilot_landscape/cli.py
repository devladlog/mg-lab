"""Command line: `python -m copilot_landscape catalog|audit`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import catalog as cat
from . import licence_audit as la


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="copilot_landscape", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("catalog", help="print the verified Copilot catalog")
    c.add_argument("--area", help="only this area (m365, azure, power-bi, ...)")
    c.add_argument("--free", action="store_true", help="only what needs no purchase")
    c.add_argument("--markdown", action="store_true", help="markdown table instead of text")
    c.add_argument("--validate", action="store_true", help="validate the catalog file and exit")

    a = sub.add_parser("audit", help="which Copilot licences does the tenant hold?")
    src = a.add_mutually_exclusive_group(required=True)
    src.add_argument("--skus", help="JSON file with the Graph subscribedSkus response")
    src.add_argument("--graph-token-env", metavar="VAR", help="name of an env var holding a Graph access token")
    a.add_argument("--graph-base", default=la.GRAPH_BASE, help=argparse.SUPPRESS)
    a.add_argument("--json", action="store_true", help="JSON output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "catalog":
        data = cat.load_catalog()
        if args.validate:
            problems = cat.validate(data)
            for problem in problems:
                print(problem, file=sys.stderr)
            print(f"{len(data['entries'])} entries, {len(problems)} problem(s)")
            return 1 if problems else 0
        items = cat.entries(data, area=args.area, free_only=args.free)
        print(cat.to_markdown(items) if args.markdown else cat.to_text(items))
        return 0

    if args.skus:
        skus = la.load_skus(args.skus)
    else:
        token = os.environ.get(args.graph_token_env)
        if not token:
            print(f"environment variable {args.graph_token_env} is empty", file=sys.stderr)
            return 2
        skus = la.fetch_skus(token, base_url=args.graph_base)
    report = la.audit(skus)
    print(json.dumps(report, indent=2) if args.json else la.format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
