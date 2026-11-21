"""python -m casekit doctor | seed | triage | sla | resolve

doctor                     read $metadata: Customer Service tables, CloseIncident, the case's KPI lookups
seed [--apply]             create the demo cases (fictional customer 'Contoso Retail'); dry run by default
triage [--from-json F]     open cases against the team's own targets (service.json); exit 1 on errors
sla                        what the platform's SLA KPI instances say for each open case
resolve CASE_ID [--apply]  CloseIncident (Problem Solved); dry run by default
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import cases, doctor, sla
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "service.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def now_of(args) -> dt.datetime:
    return (cases.parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc))


def cmd_triage(args, cfg, out=print) -> int:
    if args.from_json:
        rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))["value"]
        data = [cases.to_case(r) for r in rows]
    else:
        data = cases.fetch_open(make_api(args))
    now = now_of(args)
    for line in cases.summary(data, now):
        out(line)
    out("")
    findings = cases.triage(data, now, cfg)
    for f in findings:
        out(str(f))
    errors = sum(f.level == "error" for f in findings)
    out(f"{errors} error(s), {sum(f.level == 'warning' for f in findings)} warning(s)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casekit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    s = sub.add_parser("seed")
    s.add_argument("--file", default=str(EPISODE / "sample" / "demo-cases.json"))
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("triage")
    s.add_argument("--from-json")
    s.add_argument("--now", help="ISO time, e.g. 2027-01-15T12:00:00Z (for repeatable output)")
    sub.add_parser("sla")
    s = sub.add_parser("resolve")
    s.add_argument("case_id")
    s.add_argument("--subject", default="Case resolved")
    s.add_argument("--description", default="")
    s.add_argument("--info-provided", action="store_true", help="status 1000 instead of 5")
    s.add_argument("--apply", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    try:
        if args.cmd == "triage":
            return cmd_triage(args, cfg)
        api = make_api(args)
        if args.cmd == "doctor":
            return doctor.check(api)
        if args.cmd == "seed":
            specs = json.loads(Path(args.file).read_text(encoding="utf-8"))
            n = cases.seed(api, specs, cfg, apply=args.apply)
            print(f"{n} case(s) {'created' if args.apply else 'would be created'}")
            return 0
        if args.cmd == "sla":
            for line in sla.report(sla.rows(api)):
                print(line)
            return 0
        if args.cmd == "resolve":
            cases.resolve(api, args.case_id, args.subject, args.description,
                          cases.STATUS_INFO_PROVIDED if args.info_provided else cases.STATUS_PROBLEM_SOLVED,
                          apply=args.apply)
            return 0
    except (DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
    return 2
