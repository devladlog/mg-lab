"""python -m salesctl doctor | pipeline | hygiene | leads | qualify | close

doctor                       read $metadata: are the Sales tables and the actions we call there, and how are they bound?
pipeline [--from-json F]     open pipeline by close month and forecast category, count, value, weighted value
hygiene  [--from-json F]     opportunities that break the rules (past or missing close date, no revenue, stale...); exit 1 on errors
leads    [--email E]         open leads (find the id to qualify)
qualify  LEAD_ID [--apply]   QualifyLead: account + contact + opportunity (flags to turn each off); dry run by default
close    OPP_ID --won|--lost [--revenue N] [--apply]   WinOpportunity / LoseOpportunity; dry run by default
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import close as closer, doctor, lead, pipeline
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "sales.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def load_deals(args) -> List[pipeline.Deal]:
    if args.from_json:
        rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))["value"]
        return [pipeline.to_deal(r) for r in rows]
    return pipeline.fetch_open(make_api(args), args.owner)


def today(args) -> dt.date:
    return dt.date.fromisoformat(args.now) if args.now else dt.date.today()


def cmd_pipeline(args, cfg, out=print) -> int:
    for line in pipeline.report(load_deals(args), today(args), cfg["currency"]):
        out(line)
    return 0


def cmd_hygiene(args, cfg, out=print) -> int:
    deals = load_deals(args)
    findings = pipeline.hygiene(deals, today(args), stale_days=cfg["stale_days"], large_deal=cfg["large_deal"],
                                soon_days=cfg["soon_days"])
    for f in findings:
        out(str(f))
    errors = sum(f.level == "error" for f in findings)
    out(f"{len(deals)} open opportunities: {errors} error(s), {len(findings) - errors} warning(s)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="salesctl", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    for name in ("pipeline", "hygiene"):
        s = sub.add_parser(name)
        s.add_argument("--from-json")
        s.add_argument("--owner", help="owner (systemuser) GUID; default: everyone you can read")
        s.add_argument("--now", help="today, YYYY-MM-DD (for repeatable output)")
    s = sub.add_parser("leads")
    s.add_argument("--email")
    s.add_argument("--topic")
    s = sub.add_parser("qualify")
    s.add_argument("lead_id")
    s.add_argument("--no-account", action="store_true")
    s.add_argument("--no-contact", action="store_true")
    s.add_argument("--no-opportunity", action="store_true")
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("close")
    s.add_argument("opportunity_id")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--won", action="store_true")
    g.add_argument("--lost", action="store_true")
    s.add_argument("--revenue", type=float)
    s.add_argument("--description", default="")
    s.add_argument("--competitor-id")
    s.add_argument("--apply", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    try:
        if args.cmd == "pipeline":
            return cmd_pipeline(args, cfg)
        if args.cmd == "hygiene":
            return cmd_hygiene(args, cfg)
        api = make_api(args)
        if args.cmd == "doctor":
            return doctor.check(api)
        if args.cmd == "leads":
            rows = lead.find_open(api, args.email, args.topic)
            for r in rows:
                print(f"{r['leadid']}  {r.get('subject', '')}  {r.get('companyname') or ''}  {r.get('emailaddress1') or ''}")
            print(f"{len(rows)} open lead(s)")
            return 0
        if args.cmd == "qualify":
            lead.qualify(api, args.lead_id, account=not args.no_account, contact=not args.no_contact,
                         opportunity=not args.no_opportunity, apply=args.apply)
            return 0
        if args.cmd == "close":
            closer.close(api, args.opportunity_id, won=args.won, revenue=args.revenue,
                         description=args.description, competitor_id=args.competitor_id, apply=args.apply)
            return 0
    except (DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
    return 2
