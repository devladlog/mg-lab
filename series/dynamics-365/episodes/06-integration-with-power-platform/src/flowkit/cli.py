"""python -m flowkit envvars | pull | lint | runs | settings | connrefs | restart

envvars  [--set NAME=VALUE]   create the environment variable definitions (in the solution) and set values (outside it)
pull     [--out FILE]         read the flow's clientdata from Dataverse and save it as pretty JSON for source control
lint     [--file FILE]        check the flow definition (default: pull it first); exit 1 on errors
runs     [--days N]           run history from the FlowRun table; --from-json for the offline sample
settings [--file F] [--out F] deployment settings skeleton for the next environment; --check F validates one
connrefs                      connection references in the environment and whether each has a connection
restart                       turn the flow off and on (statecode 0 -> 1): needed after changing an env var value
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import definition, envvars, runs, settings
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "flow.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args, solution: Optional[str] = None) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env), solution=solution)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cmd_pull(api: WebApi, cfg, out_file: Optional[Path], out=print) -> definition.Flow:
    row = runs.find_flow(api, cfg["flow_name"], with_clientdata=True)
    data = definition.load_clientdata(row["clientdata"])
    path = out_file or EPISODE / "flows" / f"{slug(cfg['flow_name'])}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state = {0: "Off (Draft)", 1: "On", 2: "Suspended"}.get(row.get("statecode"), "?")
    out(f"{cfg['flow_name']}  ({state}, modified {str(row.get('modifiedon', ''))[:19]})  -> {path.name}")
    flow = definition.Flow(data)
    for line in flow.summary():
        out(f"  {line}")
    return flow


def cmd_lint(flow: definition.Flow, cfg, out=print) -> int:
    findings = definition.lint(flow, cfg)
    for f in findings:
        out(str(f))
    errors = sum(f.level == "error" for f in findings)
    warnings = sum(f.level == "warning" for f in findings)
    out(f"{errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def cmd_connrefs(api: WebApi, out=print) -> int:
    rows = list(api.get_all("connectionreferences?$select=connectionreferencelogicalname,connectionreferencedisplayname,"
                            "connectorid,connectionid,statecode&$orderby=connectionreferencelogicalname"))
    missing = 0
    for r in rows:
        has = bool(r.get("connectionid"))
        missing += not has
        out(f"  {r.get('connectionreferencelogicalname', ''):<48} {str(r.get('connectorid', '')).rsplit('/', 1)[-1]:<34} "
            f"{'connected' if has else 'NO CONNECTION'}")
    out(f"{len(rows)} connection reference(s), {missing} without a connection")
    return 1 if missing else 0


def cmd_restart(api: WebApi, cfg, out=print) -> int:
    row = runs.find_flow(api, cfg["flow_name"])
    path = f"workflows({row['workflowid']})"
    api.update(path, {"statecode": 0}, in_solution=False)
    api.update(path, {"statecode": 1}, in_solution=False)
    out(f"{cfg['flow_name']}: turned off and on (picks up current environment variable values)")
    return 0


def read_flow_file(p: Path) -> definition.Flow:
    return definition.Flow(definition.load_clientdata(p.read_text(encoding="utf-8")))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="flowkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-url", help="defaults to $DATAVERSE_URL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("envvars")
    p.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    p = sub.add_parser("pull")
    p.add_argument("--out", type=Path)
    p = sub.add_parser("lint")
    p.add_argument("--file", type=Path, help="a saved clientdata JSON (offline)")
    p = sub.add_parser("runs")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--from-json", type=Path, help="FlowRun rows saved as JSON (offline)")
    p = sub.add_parser("settings")
    p.add_argument("--file", type=Path, help="flow clientdata JSON (default: pull)")
    p.add_argument("--out", type=Path)
    p.add_argument("--check", type=Path, help="validate an existing settings file")
    sub.add_parser("connrefs")
    sub.add_parser("restart")
    args = ap.parse_args(argv)
    cfg = load_config()

    try:
        if args.cmd == "lint" and args.file:
            return cmd_lint(read_flow_file(args.file), cfg)
        if args.cmd == "runs" and args.from_json:
            rows = json.loads(args.from_json.read_text(encoding="utf-8"))
            rows = rows.get("value", rows) if isinstance(rows, dict) else rows
            for line in runs.report(cfg["flow_name"], rows, args.days):
                print(line)
            return 0
        if args.cmd == "settings" and (args.check or args.file):
            flow = read_flow_file(args.file) if args.file else None
            if args.check:
                problems = settings.check(json.loads(args.check.read_text(encoding="utf-8")), flow, cfg)
                for pr in problems:
                    print(f"! {pr}")
                print("OK: ready for an unattended import" if not problems else f"{len(problems)} problem(s)")
                return 1 if problems else 0
            body = settings.build(flow, cfg)
            text = json.dumps(body, indent=2) + "\n"
            (args.out.write_text(text, encoding="utf-8") if args.out else print(text, end=""))
            return 0

        if args.cmd == "envvars":
            envvars.ensure(make_api(args, cfg["solution"]), cfg, envvars.parse_assignments(args.set))
            return 0
        api = make_api(args)
        if args.cmd == "pull":
            cmd_pull(api, cfg, args.out)
            return 0
        if args.cmd == "lint":
            return cmd_lint(cmd_pull(api, cfg, None, out=lambda s: None), cfg)
        if args.cmd == "runs":
            row = runs.find_flow(api, cfg["flow_name"])
            for line in runs.report(cfg["flow_name"], runs.fetch(api, row["workflowid"], days=args.days), args.days):
                print(line)
            return 0
        if args.cmd == "settings":
            flow = cmd_pull(api, cfg, None, out=lambda s: None)
            body = settings.build(flow, cfg)
            text = json.dumps(body, indent=2) + "\n"
            (args.out.write_text(text, encoding="utf-8") if args.out else print(text, end=""))
            return 0
        if args.cmd == "connrefs":
            return cmd_connrefs(api)
        if args.cmd == "restart":
            return cmd_restart(api, cfg)
    except (DataverseError, LookupError, ValueError) as e:
        print(f"error: {e}")
        return 2
    return 0
