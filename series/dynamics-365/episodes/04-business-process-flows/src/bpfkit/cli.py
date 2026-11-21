"""python -m bpfkit stages | status | next | back | finish | abandon | backfill | report

stages            the BPF definition: instance table, lookup, stages (as stored, unordered)
status   --code   every BPF on the record (RetrieveProcessInstances) + this BPF's active path with markers
next     --code   move one stage forward along the active path      (--dry-run: show the PATCH only)
back     --code   move back to the previous stage
finish   --code   mark the instance Finished (last stage only)
abandon  --code   mark the instance Aborted
backfill          records with no instance (created before activation): list, or --apply to create them
report            stage report from the BPF table; --from-json for the offline sample; --fail-on-stuck for CI
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import backfill, definition, instances, path, report
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "bpf.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def cmd_stages(d: definition.BpfDefinition, out=print) -> None:
    out(f"{d.name}  (workflow {d.workflow_id}, {'Activated' if d.activated else 'Draft'})")
    out(f"instance table {d.unique_name}  entity set {d.entity_set}  lookup {d.lookup} -> nav {d.nav}")
    for s in d.stages:
        out(f"  stage {s.name:<16} {s.id}  {s.entity}")
    out("note: processstage rows have no guaranteed order; `status` shows the real path of a record")


def cmd_status(api: WebApi, d: definition.BpfDefinition, cfg, code: str, out=print) -> int:
    rec = instances.find_record(api, cfg["entity_set"], cfg["key"], code, cfg["table"])
    rid = rec[f"{cfg['table']}id"]
    out(f"{code}  {rec.get('mgl_name', '')}")
    for p in instances.all_processes_for(api, cfg["table"], rid):
        stage = p.get("processstageid")
        out(f"  process instance: {p.get('name', '?')}  active stage {d.stage_name(stage) if stage else '?'}")
    insts = instances.instances_for(api, d, rid)
    if not insts:
        out(f"  no '{d.name}' instance: created before the BPF was activated? run `backfill`")
        return 1
    inst = insts[0]
    stages = instances.active_path(api, inst.id)
    visited = set(path.parse_traversed(inst.traversed))
    marks = []
    for s in stages:
        sid = path.norm(s["processstageid"])
        mark = ">" if sid == inst.stage_id else ("x" if sid in visited else " ")
        marks.append(f"[{mark}] {s.get('stagename') or d.stage_name(sid)}")
    out(f"  {d.name}: {inst.state}, stage since {inst.stage_started or '?'}")
    out("  active path: " + "  ".join(marks))
    return 0


def _instance(api, d, cfg, code) -> instances.Instance:
    rec = instances.find_record(api, cfg["entity_set"], cfg["key"], code, cfg["table"])
    insts = instances.instances_for(api, d, rec[f"{cfg['table']}id"])
    if not insts:
        raise path.StageMoveError(f"{code} has no '{d.name}' instance: run `backfill --apply` first")
    return insts[0]


def cmd_move(api, d, cfg, code: str, direction: str, dry_run: bool, out=print) -> int:
    inst = _instance(api, d, cfg, code)
    mv = instances.move(api, d, inst, direction, dry_run=dry_run)
    verb = "would move" if dry_run else "moved"
    out(f"{code}: {verb} {d.stage_name(inst.stage_id)} -> {d.stage_name(mv.target)}")
    out(f"  PATCH {d.entity_set}({inst.id}) {json.dumps(mv.payload())}")
    return 0


def cmd_report(args, cfg, out=print) -> int:
    today = date.fromisoformat(args.now) if args.now else date.today()
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        names = {path.norm(s["processstageid"]): s["stagename"] for s in data["stages"]}
        rows = report.rows_from_api(data["instances"], names, data["lookup_value"], data["nav"], cfg["key"])
        bpf_name = data.get("bpf", cfg["bpf"])
    else:
        api = make_api(args)
        d = definition.load(api, cfg["bpf"], cfg["table"])
        raw = api.get_all(f"{d.entity_set}?$select={instances.INSTANCE_SELECT},{d.lookup_value}"
                          f"&$expand={d.nav}($select={cfg['key']})")
        rows = report.rows_from_api(raw, d.names(), d.lookup_value, d.nav, cfg["key"])
        bpf_name = d.name
    order = cfg.get("stage_order") or sorted({r.stage for r in rows})
    rep = report.build(bpf_name, rows, order, cfg["stuck_days"], today)
    for line in report.render(rep, cfg["stuck_days"], today):
        out(line)
    return 1 if (args.fail_on_stuck and rep.stuck) else 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="bpfkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-url", help="environment URL (default: $DATAVERSE_URL)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stages")
    for name in ("status", "next", "back", "finish", "abandon"):
        sp = sub.add_parser(name)
        sp.add_argument("--code", required=True, help="request code, e.g. PR-0004")
        if name in ("next", "back"):
            sp.add_argument("--dry-run", action="store_true")
    bf = sub.add_parser("backfill")
    bf.add_argument("--apply", action="store_true", help="create the missing instances (default: list only)")
    rp = sub.add_parser("report")
    rp.add_argument("--from-json", help="offline: instances + stages in Web API shape (see sample/)")
    rp.add_argument("--now", help="report date YYYY-MM-DD (default: today)")
    rp.add_argument("--fail-on-stuck", action="store_true", help="exit 1 when any request is stuck")
    args = p.parse_args(argv)
    cfg = load_config()

    try:
        if args.cmd == "report":
            return cmd_report(args, cfg)
        api = make_api(args)
        d = definition.load(api, cfg["bpf"], cfg["table"])
        if args.cmd == "stages":
            cmd_stages(d)
            return 0
        if args.cmd == "status":
            return cmd_status(api, d, cfg, args.code)
        if args.cmd in ("next", "back"):
            return cmd_move(api, d, cfg, args.code, args.cmd, args.dry_run)
        if args.cmd in ("finish", "abandon"):
            inst = _instance(api, d, cfg, args.code)
            (instances.finish if args.cmd == "finish" else instances.abandon)(api, d, inst)
            print(f"{args.code}: {'Finished' if args.cmd == 'finish' else 'Aborted'} at {d.stage_name(inst.stage_id)}")
            return 0
        if args.cmd == "backfill":
            plan = backfill.plan(api, d, cfg)
            print(f"{len(plan.missing)} active record(s) without a '{d.name}' instance")
            for r in plan.missing:
                print(f"  {r['code']}")
            if args.apply and plan.missing:
                backfill.apply(api, d, cfg, plan)
                print(f"created {len(plan.created)}, failed {len(plan.failed)}")
                return 1 if plan.failed else 0
            return 0
    except (DataverseError, path.StageMoveError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
