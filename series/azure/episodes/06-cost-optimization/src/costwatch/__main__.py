"""costwatch: price a deployment before it ships, find what's left running after.

  python -m costwatch estimate whatif.json --budget 60 [--summary out.md]
      exit 0 within budget, 1 over budget, 2 can't price (no price, ambiguous price, bad what-if)
  python -m costwatch waste [--subscriptions ID ...] [--max-waste 5]
      exit 0, or 1 when the priced waste per month is above --max-waste
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import estimate as est
from . import waste
from .prices import PriceError, RetailPrices


def _prices(args: argparse.Namespace) -> RetailPrices:
    return RetailPrices(currency=args.currency, cache_file=Path(args.cache) if args.cache else None)


def cmd_estimate(args: argparse.Namespace) -> int:
    try:
        doc = json.loads(Path(args.whatif).read_text())
        result = est.estimate(est.resources_from_whatif(doc), _prices(args))
    except (PriceError, ValueError, json.JSONDecodeError) as e:
        print(f"costwatch: can't estimate: {e}", file=sys.stderr)
        return 2
    report = est.to_markdown(result, args.budget)
    print(report)
    if args.summary:
        Path(args.summary).write_text("## Cost estimate\n\n" + report + "\n")
    if args.budget is not None and result.monthly_total > args.budget:
        print(f"##vso[task.logissue type=error]Estimated {result.monthly_total:.2f} {result.currency}/month "
              f"is over the {args.budget:.2f} budget", file=sys.stderr)
        return 1
    return 0


def _table(rows: list[dict]) -> str:
    if not rows:
        return "(none)"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def cmd_waste(args: argparse.Namespace) -> int:
    try:
        report = waste.find_waste(_prices(args), args.az, args.subscriptions)
        untagged = waste.run_graph_query((waste.QUERY_DIR / "untagged-by-type.kql").read_text(), args.az, args.subscriptions)
        advisor = waste.run_graph_query((waste.QUERY_DIR / "advisor-cost-savings.kql").read_text(), args.az, args.subscriptions)
    except (waste.AzError, PriceError) as e:
        print(f"costwatch: {e}", file=sys.stderr)
        return 2
    print(waste.to_markdown(report))
    print("\n### No workload tag (can't be charged back)\n" + _table(untagged))
    print("\n### Azure Advisor cost recommendations\n" + _table(advisor))
    if args.max_waste is not None and report.monthly_total > args.max_waste:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="costwatch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--currency", default="EUR")
    ap.add_argument("--cache", help="JSON file to cache Retail Prices API answers (the API is rate-limited)")
    sub = ap.add_subparsers(dest="command", required=True)

    e = sub.add_parser("estimate", help="price an az deployment what-if result (JSON)")
    e.add_argument("whatif")
    e.add_argument("--budget", type=float, help="monthly budget; exit 1 when the estimate is above it")
    e.add_argument("--summary", help="also write the table to this Markdown file (pipeline summary)")
    e.set_defaults(func=cmd_estimate)

    w = sub.add_parser("waste", help="Resource Graph: orphaned and idle resources, with a monthly price")
    w.add_argument("--subscriptions", nargs="*")
    w.add_argument("--az", default="az", help="Azure CLI executable")
    w.add_argument("--max-waste", type=float)
    w.set_defaults(func=cmd_waste)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
