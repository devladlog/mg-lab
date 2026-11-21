"""python -m apikit check | deploy | call | backfill | jobs | trace | workflows | remove

check                 validate plugins.json against Learn's rules (offline)
deploy                column, assembly, plug-in types, custom API, async steps + post-images (idempotent, in the solution)
call      --code      run the custom API on one request (POST .../Microsoft.Dynamics.CRM.mgl_AssessProjectRequest)
backfill  [--apply]   score active requests that have no mgl_riskscore yet (saved before the step existed)
jobs      [--failed]  system jobs of our async steps (asyncoperation by _owningextensionid_value)
trace                 last plug-in trace log rows for the assembly
workflows [--all]     classic workflows and actions in the environment, with where each should go
remove                delete steps, custom API, types and assembly (keeps the column)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import deploy, ops, registration
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "plugins.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args, solution: Optional[str] = None) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env), solution=solution)


def cmd_check(cfg, out=print) -> int:
    problems = registration.validate(cfg)
    for p in problems:
        out(f"! {p}")
    api = cfg["custom_api"]
    out(f"custom API {api['uniquename']}: {'Function' if api['isfunction'] else 'Action'}, "
        f"bound to {api.get('boundentitylogicalname') or '(global)'}, "
        f"{len(api['response_properties'])} response properties, private={api['isprivate']}")
    for s in cfg["steps"]:
        out(f"step {s['message']:<7} {registration.STAGES[s['stage']]} {registration.MODES[s['mode']]}"
            + (f"  filtering {','.join(s['filteringattributes'])}" if s.get("filteringattributes") else "")
            + (f"  post-image {','.join(s['post_image'])}" if s.get("post_image") else ""))
    out("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="apikit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-url", help="defaults to $DATAVERSE_URL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("deploy")
    p = sub.add_parser("call")
    p.add_argument("--code", required=True)
    p = sub.add_parser("backfill")
    p.add_argument("--apply", action="store_true")
    p = sub.add_parser("jobs")
    p.add_argument("--failed", action="store_true")
    p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("trace")
    p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("workflows")
    p.add_argument("--all", action="store_true", help="include managed (system/app) processes")
    p.add_argument("--table")
    sub.add_parser("remove")
    args = ap.parse_args(argv)
    cfg = load_config()

    if args.cmd == "check":
        return cmd_check(cfg)
    try:
        if args.cmd == "deploy":
            deploy.deploy(make_api(args, cfg["solution"]), cfg, deploy.read_dll(EPISODE, cfg))
            return 0
        api = make_api(args)
        if args.cmd == "call":
            ops.cmd_call(api, cfg, args.code)
            return 0
        if args.cmd == "backfill":
            return ops.cmd_backfill(api, cfg, apply=args.apply)
        if args.cmd == "jobs":
            return ops.cmd_jobs(api, cfg, failed_only=args.failed, top=args.top)
        if args.cmd == "trace":
            return ops.cmd_trace(api, cfg, top=args.top)
        if args.cmd == "workflows":
            return ops.cmd_workflows(api, include_managed=args.all, table=args.table)
        if args.cmd == "remove":
            deploy.remove(api, cfg)
            return 0
    except (DataverseError, registration.ConfigError) as e:
        print(f"error: {e}")
        return 2
    return 0
