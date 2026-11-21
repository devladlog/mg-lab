"""python -m adminkit settings | jobs | admins | audit-on

settings [--from-json F]       environment settings (auditing, trace log, timeouts) against the team policy
jobs     [--from-json F]       failed and stuck system jobs
admins   [--from-json F]       who holds System Administrator (people, disabled users, teams, application users)
audit-on [--days N] [--apply]  turn environment auditing on and set retention; dry run by default

Every report command exits 1 when it finds an error, so a scheduled run can fail on it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import admins, jobs, settings
from .findings import Finding, exit_code, tally
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "admin.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now_of(args) -> dt.datetime:
    return jobs.parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)


def finish(findings: List[Finding], out=print) -> int:
    out("")
    for f in findings:
        out(str(f))
    out(tally(findings))
    return exit_code(findings)


def cmd_settings(args, cfg, out=print) -> int:
    org = read_json(args.from_json)["value"][0] if args.from_json else settings.fetch(make_api(args))
    for line in settings.describe(org):
        out(line)
    return finish(settings.check(org, cfg), out)


def cmd_jobs(args, cfg, out=print) -> int:
    now = now_of(args)
    rows = read_json(args.from_json)["value"] if args.from_json else jobs.fetch(make_api(args), now, cfg)
    for line in jobs.summary(rows, now, cfg):
        out(line)
    return finish(jobs.analyse(rows, now, cfg), out)


def cmd_admins(args, cfg, out=print) -> int:
    roles = read_json(args.from_json)["value"] if args.from_json else admins.fetch(make_api(args), cfg)
    for line in admins.table(roles, cfg):
        out(line)
    return finish(admins.analyse(roles, cfg), out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adminkit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("settings", "jobs", "admins"):
        s = sub.add_parser(name)
        s.add_argument("--from-json", help="read a saved Web API response instead of calling the environment")
        if name == "jobs":
            s.add_argument("--now", help="ISO time, e.g. 2027-01-15T12:00:00Z (for repeatable output)")
    s = sub.add_parser("audit-on")
    s.add_argument("--days", type=int, default=365, help="retention in days; -1 = forever (default 365)")
    s.add_argument("--apply", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    try:
        if args.cmd == "settings":
            return cmd_settings(args, cfg)
        if args.cmd == "jobs":
            return cmd_jobs(args, cfg)
        if args.cmd == "admins":
            return cmd_admins(args, cfg)
        if args.cmd == "audit-on":
            settings.enable_audit(make_api(args), args.days, apply=args.apply)
            return 0
    except (DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
    return 2
