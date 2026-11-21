"""python -m fokit doctor | customers | reconcile

doctor                         token + one OData call: is the endpoint, the app registration and the entity reachable?
customers [--company ID]       customers over OData (cross-company=true), summary by company
reconcile                      finance and operations customers vs Dataverse accounts, by account number; exit 1 on errors

Environment: FO_URL (https://<environment>.operations.dynamics.com), DATAVERSE_URL (reconcile only),
AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET (optional, see auth.py).
Offline: --fo-json and --dv-json read saved responses (sample/) instead of calling the services.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import customers, reconcile
from .dataverse import DataverseApi, DataverseError
from .findings import exit_code, tally
from .fo import FoApi, FoError

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "fo.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def need(args_value: Optional[str], env: str, what: str) -> str:
    v = args_value or os.environ.get(env)
    if not v:
        raise SystemExit(f"set {env} ({what})")
    return v


def make_fo(args) -> FoApi:
    from .auth import token_provider
    url = need(args.fo_url, "FO_URL", "https://<environment>.operations.dynamics.com")
    return FoApi(url, token_provider(url))


def make_dv(args) -> DataverseApi:
    from .auth import token_provider
    url = need(args.dataverse_url, "DATAVERSE_URL", "https://<org>.crm4.dynamics.com")
    return DataverseApi(url, token_provider(url, dataverse=True))


def read_json(path: str) -> List[Dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["value"]


def load_fo(args, cfg) -> List[customers.FoCustomer]:
    if args.fo_json:
        rows = [customers.to_customer(r) for r in read_json(args.fo_json)]
        company = getattr(args, "company", None)
        return [c for c in rows if c.company == company] if company else rows
    return customers.fetch_customers(make_fo(args), cfg, getattr(args, "company", None))


def cmd_doctor(args, cfg, out=print) -> int:
    api = make_fo(args)
    url = customers.fo_url(api, cfg, top=1)
    out(f"GET {url}")
    rows = list(api.get_all(url))
    out(f"ok: {cfg['entity']} answered with {len(rows)} row(s); columns {', '.join(sorted(rows[0])) if rows else '-'}")
    return 0


def cmd_customers(args, cfg, out=print) -> int:
    data = load_fo(args, cfg)
    by_company = Counter(c.company for c in data)
    out(f"{len(data)} customer(s)")
    for company, n in sorted(by_company.items()):
        out(f"  {company or '(none)':8} {n}")
    for c in data[: args.limit]:
        out(f"  {c.company:6} {c.account:12} {c.party_type:13} {c.name}")
    return 0


def cmd_reconcile(args, cfg, out=print) -> int:
    fo = load_fo(args, cfg)
    dv = ([customers.to_account(r) for r in read_json(args.dv_json)] if args.dv_json
          else customers.fetch_accounts(make_dv(args), cfg))
    org = cfg["organization_party_type"]
    for line in reconcile.summary(fo, dv, org):
        out(line)
    findings = reconcile.reconcile(fo, dv, org)
    out("")
    for f in findings:
        out(str(f))
    out(tally(findings))
    return exit_code(findings)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fokit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--fo-url")
    p.add_argument("--dataverse-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    s = sub.add_parser("customers")
    s.add_argument("--company", help="one legal entity (dataAreaId), e.g. usmf")
    s.add_argument("--fo-json")
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("reconcile")
    s.add_argument("--company")
    s.add_argument("--fo-json")
    s.add_argument("--dv-json")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    try:
        return {"doctor": cmd_doctor, "customers": cmd_customers, "reconcile": cmd_reconcile}[args.cmd](args, cfg)
    except (FoError, DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
