"""CLI: python -m whatif_gate --whatif whatif.json --policy gate-policy.json [--summary out.md] [--azure-devops]"""
from __future__ import annotations

import argparse
import json
import sys

from .gate import Policy, WhatIfFormatError, evaluate, logging_commands, to_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="whatif_gate", description=__doc__)
    ap.add_argument("--whatif", required=True, help="JSON from 'az deployment group what-if --no-pretty-print'")
    ap.add_argument("--policy", required=True, help="gate policy JSON")
    ap.add_argument("--summary", help="write a Markdown summary to this file")
    ap.add_argument("--title", default="What-if gate")
    ap.add_argument("--accept-protected", action="store_true",
                    help="let protected changes through (recorded in the summary)")
    ap.add_argument("--azure-devops", action="store_true",
                    help="print ##vso logging commands and upload the summary to the run")
    args = ap.parse_args(argv)

    with open(args.policy, encoding="utf-8") as fh:
        policy = Policy.from_dict(json.load(fh))
    try:
        with open(args.whatif, encoding="utf-8") as fh:
            doc = json.load(fh)
        result = evaluate(doc, policy, accept_protected=args.accept_protected)
    except (WhatIfFormatError, json.JSONDecodeError) as exc:
        print(f"what-if output unusable: {exc}", file=sys.stderr)
        if args.azure_devops:
            print(f"##vso[task.logissue type=error]what-if output unusable: {str(exc).splitlines()[0]}")
        return 2

    md = to_markdown(result, args.title)
    print(md)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as fh:
            fh.write(md)
    if args.azure_devops:
        for line in logging_commands(result):
            print(line)
        if args.summary:
            print(f"##vso[task.uploadsummary]{args.summary}")
    return 1 if result.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
