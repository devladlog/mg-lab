"""python -m reportkit queries | pipeline | monthly | reconcile | chart

queries                       print the FetchXML and the OData $apply used (no environment needed)
pipeline [--from-json F]      open opportunities by group (default forecast category); --csv to write the table
monthly  [--from-json F]      open opportunities by estimated close month (FetchXML dategrouping, UTC)
reconcile [--by COLUMN]       the same totals from rows, FetchXML and $apply; exit 1 if they disagree
chart pipeline|revenue [--apply]   create the user chart in the environment (dry run by default)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from . import charts, queries as Q, reports
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]
DEFAULT_BY = "msdyn_forecastcategory"


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def _rows(path: str) -> list:
    return json.loads(Path(path).read_text(encoding="utf-8"))["value"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reportkit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("queries")
    s.add_argument("--by", default=DEFAULT_BY)
    s = sub.add_parser("pipeline")
    s.add_argument("--by", default=DEFAULT_BY)
    s.add_argument("--from-json")
    s.add_argument("--csv")
    s = sub.add_parser("monthly")
    s.add_argument("--from-json")
    s = sub.add_parser("reconcile")
    s.add_argument("--by", default=DEFAULT_BY)
    s = sub.add_parser("chart")
    s.add_argument("which", choices=sorted(charts.BUILDERS))
    s.add_argument("--apply", action="store_true")
    return p


def main(argv: Optional[List[str]] = None, out=print) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "queries":
            out("FetchXML (statecode 0, grouped):\n  " + Q.fetch_by_column(args.by))
            out("OData:\n  " + Q.apply_by_column(args.by))
            out("FetchXML by month (OData groupby with datetime isn't supported):\n  " + Q.fetch_by_month())
            return 0
        if args.cmd == "pipeline":
            if args.from_json:
                rep = Q.from_client_rows([r for r in _rows(args.from_json)], args.by)
                out("(client-side from the JSON file: no environment, so nothing to reconcile)")
            else:
                rep = Q.from_fetch_rows(Q.run_fetch(make_api(args), Q.fetch_by_column(args.by)))
            reports.table(rep, "forecast category" if args.by == DEFAULT_BY else args.by, out)
            if args.csv:
                reports.write_csv(rep, Path(args.csv))
                out(f"wrote {args.csv}")
            return 0
        if args.cmd == "monthly":
            if args.from_json:
                rep = Q.from_client_month_rows(_rows(args.from_json))
                out("(client-side from the JSON file: no environment, so nothing to reconcile)")
            else:
                rep = Q.from_fetch_month_rows(Q.run_fetch(make_api(args), Q.fetch_by_month()))
            reports.table(rep, "estimated close month", out)
            return 0
        api = make_api(args)
        if args.cmd == "reconcile":
            bad = reports.reconcile(reports.category_three_ways(api, args.by), out)
            bad += reports.reconcile(reports.month_two_ways(api), out)
            return 1 if bad else 0
        if args.cmd == "chart":
            charts.create(api, charts.BUILDERS[args.which](), apply=args.apply, out=out)
            return 0
    except Q.AggregateLimit as e:
        out(f"error: AggregateQueryRecordLimit: {e}")
        return 1
    except (DataverseError, ValueError) as e:
        out(f"error: {e}")
        return 1
    return 2
