"""python -m bckit doctor | companies | customers | invoices | seed | reconcile

doctor                         one call to the API root and to companies: is the container, the endpoint and the login ok?
companies                      the companies in the container (id, name)
customers [--company NAME]     customers per company
invoices  [--company NAME] [--status Open] [--customer NO] [--top N]   sales invoices (posted and unposted)
seed --company NAME [--dry-run]  create the fictional Contoso demo customers (writes to the local container only)
reconcile                      Business Central customers vs Dataverse accounts, by number; exit 1 on errors

Environment: BC_PASSWORD (required for live calls), BC_USER (default admin), BC_BASE_URL (default http://mglab-bc:7048/BC),
DATAVERSE_URL (reconcile only), AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET (optional, see auth.py).
`New-LabBusinessCentral.ps1 -SetEnv` sets the BC_* variables for the current PowerShell session without printing the password.
Offline: --bc-json and --dv-json read saved responses (sample/) instead of calling the services.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import customers, reconcile
from .bc import BcApi, BcError
from .dataverse import DataverseApi, DataverseError
from .findings import exit_code, tally

EPISODE = Path(__file__).resolve().parents[2]


def load_config(p: Path = EPISODE / "bc.json") -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def need(args_value: Optional[str], env: str, what: str) -> str:
    v = args_value or os.environ.get(env)
    if not v:
        raise SystemExit(f"set {env} ({what})")
    return v


def make_bc(args, cfg) -> BcApi:
    base = args.bc_url or os.environ.get("BC_BASE_URL") or cfg["base_url"]
    user = os.environ.get("BC_USER") or cfg["user"]
    password = need(None, "BC_PASSWORD", "the container admin password; New-LabBusinessCentral.ps1 -SetEnv sets it")
    return BcApi(base, user, password, api_version=cfg["api_version"])


def make_dv(args, cfg) -> DataverseApi:
    from .auth import token_provider
    url = need(args.dataverse_url, "DATAVERSE_URL", "https://<org>.crm4.dynamics.com")
    return DataverseApi(url, token_provider(url))


def read_bc_json(path: str, company: Optional[str] = None) -> List[customers.BcCustomer]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: List[customers.BcCustomer] = []
    for c in data["companies"]:
        if company and company.casefold() != c["name"].casefold():
            continue
        out += [customers.to_customer(r, c["name"]) for r in c["customers"]]
    return out


def load_bc(args, cfg) -> List[customers.BcCustomer]:
    company = getattr(args, "company", None)
    if args.bc_json:
        return read_bc_json(args.bc_json, company)
    return customers.fetch_customers(make_bc(args, cfg), cfg, company)


def load_dv(args, cfg) -> List[customers.DvAccount]:
    if args.dv_json:
        rows = json.loads(Path(args.dv_json).read_text(encoding="utf-8"))["value"]
        return [customers.to_account(r) for r in rows]
    return customers.fetch_accounts(make_dv(args, cfg), cfg)


def cmd_doctor(args, cfg, out=print) -> int:
    api = make_bc(args, cfg)
    out(f"GET {api.root}/")
    root = api.request("GET", api.root + "/") or {}
    out(f"ok: API root answered, {len(root.get('value', []))} entry(ies) in the service document")
    out(f"GET {api.companies_url()}")
    comps = customers.fetch_companies(api)
    out(f"ok: {len(comps)} company(ies): " + ", ".join(repr(c.get("name")) for c in comps))
    return 0


def cmd_companies(args, cfg, out=print) -> int:
    for c in customers.fetch_companies(make_bc(args, cfg)):
        out(f"{c.get('id')}  {c.get('name')}")
    return 0


def cmd_customers(args, cfg, out=print) -> int:
    data = load_bc(args, cfg)
    out(f"{len(data)} customer(s)")
    for company, n in sorted(Counter(c.company for c in data).items()):
        out(f"  {company or '(none)':28} {n}")
    for c in data[: args.limit]:
        out(f"  {c.number:10} {c.type:8} {c.name}" + (f"  [blocked: {c.blocked}]" if c.blocked else ""))
    return 0


def cmd_invoices(args, cfg, out=print) -> int:
    rows = customers.fetch_invoices(make_bc(args, cfg), cfg, args.company, args.status, args.customer, args.top)
    out(f"{len(rows)} sales invoice(s)")
    open_by: Dict[str, float] = defaultdict(float)
    for r in rows:
        open_by[r.customer_number] += r.remaining
    for r in rows[: args.limit]:
        out(f"  {r.number:12} {r.invoice_date:10} due {r.due_date:10} {r.status:8} {r.customer_number:8} "
            f"{r.total:12.2f} {r.currency} (remaining {r.remaining:.2f})")
    for number, amount in sorted(open_by.items(), key=lambda kv: -kv[1])[:5]:
        out(f"  remaining for {number}: {amount:.2f}")
    return 0


def cmd_seed(args, cfg, out=print) -> int:
    for line in customers.seed_customers(make_bc(args, cfg), cfg, args.company, args.dry_run):
        out(line)
    return 0


def cmd_reconcile(args, cfg, out=print) -> int:
    bc = [c for c in load_bc(args, cfg) if reconcile.in_scope(c.name, args.name_contains)]
    dv = [a for a in load_dv(args, cfg) if reconcile.in_scope(a.name, args.name_contains)]
    ct = cfg["company_type"]
    if args.name_contains:
        out(f"scope: names containing {args.name_contains!r} on both sides")
    for line in reconcile.summary(bc, dv, ct):
        out(line)
    findings = reconcile.reconcile(bc, dv, ct)
    out("")
    for f in findings:
        out(str(f))
    out(tally(findings))
    return exit_code(findings)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bckit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--bc-url", help="base URL incl. server instance, e.g. http://mglab-bc:7048/BC")
    p.add_argument("--dataverse-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("companies")
    s = sub.add_parser("customers")
    s.add_argument("--company", help="one company by name, e.g. 'CRONUS USA, Inc.'")
    s.add_argument("--bc-json")
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("invoices")
    s.add_argument("--company")
    s.add_argument("--status", help="Learn lists ' ', Draft, 'In Review', Open, Paid, Canceled, Corrective")
    s.add_argument("--customer", help="customer number")
    s.add_argument("--top", type=int)
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("seed")
    s.add_argument("--company", required=True)
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("reconcile")
    s.add_argument("--company")
    s.add_argument("--bc-json")
    s.add_argument("--dv-json")
    s.add_argument("--name-contains", help="only customers/accounts whose name contains this text, on both sides")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    cmds = {"doctor": cmd_doctor, "companies": cmd_companies, "customers": cmd_customers, "invoices": cmd_invoices,
            "seed": cmd_seed, "reconcile": cmd_reconcile}
    try:
        return cmds[args.cmd](args, cfg)
    except (BcError, DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
