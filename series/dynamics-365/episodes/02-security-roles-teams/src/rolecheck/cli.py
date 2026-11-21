"""rolecheck - explain Dataverse record access from roles, teams, business units and shares.

  python -m rolecheck explain --user "Alex Demo" --record PR-0004 --privilege Read
  python -m rolecheck who     --record PR-0001 --privilege Write
  python -m rolecheck audit
  python -m rolecheck export  --table mgl_projectrequest --out model.json      (needs an environment)
  python -m rolecheck verify  --user "Alex Demo" --record <guid> --model model.json   (needs an environment)

--model defaults to the fictional sample/contoso-security.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import model as m
from .access import explain, who_has_access
from .audit import audit

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "contoso-security.json"


def _find_user(sm: m.SecurityModel, text: str) -> str:
    if text in sm.users:
        return text
    hits = [u.id for u in sm.users.values() if u.name.lower() == text.lower()]
    if len(hits) != 1:
        raise SystemExit(f"user {text!r} not found (or ambiguous)")
    return hits[0]


def _api(args):
    from .auth import token_provider
    from .webapi import WebApi
    env = args.env_url or os.environ["DATAVERSE_URL"]
    return WebApi(env, token_provider(env))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rolecheck", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["explain", "who", "audit", "export", "verify"])
    p.add_argument("--model", type=Path, default=SAMPLE)
    p.add_argument("--user")
    p.add_argument("--record")
    p.add_argument("--privilege", default="Read", choices=m.PRIVILEGES)
    p.add_argument("--table", action="append", default=[], help="export: table logical name (repeatable)")
    p.add_argument("--out", type=Path, help="export: where to write the model JSON")
    p.add_argument("--max-records", type=int, default=50)
    p.add_argument("--env-url")
    args = p.parse_args(argv)

    if args.command == "export":
        from .export import export_model
        data = export_model(_api(args), args.table or ["mgl_projectrequest"], max_records=args.max_records,
                            warn=lambda s: print(f"warning: {s}", file=sys.stderr))
        m.from_dict(data)   # validate before writing
        text = json.dumps(data, indent=2)
        (args.out.write_text(text, encoding="utf-8") if args.out else print(text))
        print(f"exported {len(data['users'])} users, {len(data['teams'])} teams, {len(data['roles'])} roles, "
              f"{len(data['records'])} records", file=sys.stderr)
        return 0

    sm = m.load(args.model)
    if args.command == "explain":
        uid = _find_user(sm, args.user)
        rec = sm.records[args.record]
        print(f"{sm.users[uid].name} ({sm.bu_name(sm.users[uid].business_unit)}) -> {rec.table} {rec.id} "
              f"owned by {sm.principal_name(rec.owner)} ({sm.bu_name(rec.business_unit)})")
        print("\n".join(explain(sm, uid, args.record, args.privilege).lines()))
    elif args.command == "who":
        rows = who_has_access(sm, args.record, args.privilege)
        print(f"{len(rows)} user(s) can {args.privilege} {args.record}:")
        for name, path in rows:
            print(f"  {name:<16} {path}")
    elif args.command == "audit":
        findings = audit(sm)
        for f in findings:
            print(f"{f.severity:<6} {f.check:<24} {f.subject}: {f.detail}")
        print(f"{len(findings)} finding(s), {sum(f.severity == 'High' for f in findings)} high")
        return 1 if any(f.severity == "High" for f in findings) else 0
    elif args.command == "verify":
        from .verify import compare, principal_access, render
        uid = _find_user(sm, args.user)
        rec = sm.records[args.record]
        api = _api(args)
        entity_set = api.get(f"EntityDefinitions(LogicalName='{rec.table}')?$select=EntitySetName")["EntitySetName"]
        rows, same = compare(sm, principal_access(api, uid, entity_set, rec.id), uid, rec.id)
        print("\n".join(render(rows)))
        print("model matches Dataverse" if same else "model and Dataverse differ - see README 'not modelled'")
        return 0 if same else 2
    return 0
