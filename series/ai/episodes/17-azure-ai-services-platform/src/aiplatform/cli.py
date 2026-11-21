"""python -m aiplatform catalog | probe | audit | usage | lifecycle"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import audit as audit_mod
from . import catalog, lifecycle, probe, usage
from .endpoints import EndpointError
from .http import Api


def _api(args) -> Api:
    from azure.identity import DefaultAzureCredential
    return Api(DefaultAzureCredential(), retries=getattr(args, "retries", 0))


def _need(value: str | None, env: str, flag: str) -> str:
    v = value or os.environ.get(env)
    if not v:
        raise SystemExit(f"Set {env} or pass {flag}.")
    return v


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="aiplatform", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog", help="which service for which job (no Azure call)")
    c.add_argument("--task", default="")
    p = sub.add_parser("probe", help="the cheapest real call of four services with one Entra identity")
    p.add_argument("--endpoint")
    p.add_argument("--only", nargs="*", choices=list(probe.PROBES))
    p.add_argument("--retries", type=int, default=0, help="azure-core retries (default 0 so a 429 is visible)")
    a = sub.add_parser("audit", help="read the resource from ARM and check it against the rules")
    a.add_argument("--resource-id")
    u = sub.add_parser("usage", help="calls, errors and latency per API from Azure Monitor metrics")
    u.add_argument("--resource-id")
    u.add_argument("--minutes", type=int, default=60)
    lc = sub.add_parser("lifecycle", help="scan code for services with a retirement date (no Azure call)")
    lc.add_argument("path", nargs="?", default=".")
    lc.add_argument("--today", help="YYYY-MM-DD (default: today)")
    lc.add_argument("--fail-within-days", type=int, default=0)
    lc.add_argument("--include-tests", action="store_true")
    lc.add_argument("--no-lines", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build().parse_args(argv)
    try:
        if args.cmd == "catalog":
            print(catalog.render(catalog.find(catalog.load(), args.task)))
            return 0
        if args.cmd == "lifecycle":
            today = date.fromisoformat(args.today) if args.today else date.today()
            root = Path(args.path)
            if not root.exists():
                raise SystemExit(f"No such path: {root}")
            rows = lifecycle.summarise(lifecycle.scan(root, include_tests=args.include_tests), today)
            print(lifecycle.render(rows, today, show_lines=not args.no_lines))
            return lifecycle.exit_code(rows, args.fail_within_days)
        if args.cmd == "probe":
            res = probe.run_probes(_api(args), _need(args.endpoint, "AIPLATFORM_ENDPOINT", "--endpoint"), args.only)
            print(probe.render(res))
            return 0 if all(r.ok for r in res) else 1
        if args.cmd == "audit":
            f = audit_mod.audit(*audit_mod.fetch(_api(args), _need(args.resource_id, "AIPLATFORM_RESOURCE_ID", "--resource-id")))
            print(audit_mod.render(f))
            return audit_mod.exit_code(f)
        if args.cmd == "usage":
            print(usage.render(usage.query(_api(args), _need(args.resource_id, "AIPLATFORM_RESOURCE_ID", "--resource-id"), args.minutes)))
            return 0
    except (EndpointError, RuntimeError, ValueError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 2
