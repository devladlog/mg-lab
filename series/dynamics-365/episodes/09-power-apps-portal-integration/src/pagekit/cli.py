"""python -m pagekit inspect | lint | columns

inspect SITE_DIR                  what was read from the downloaded site (settings, permissions, roles)
lint SITE_DIR [--expect FILE]     Web API rules P001-P013; exit 1 on errors
columns SITE_DIR                  check each enabled table's `fields` against the environment's real columns (F001)
SITE_DIR is the folder written by `pac pages download` (the one that holds site-settings/ and table-permissions/).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from . import columns, lint as lintmod
from .siteconfig import load_site
from .webapi import DataverseError, WebApi

EPISODE = Path(__file__).resolve().parents[2]


def make_api(args) -> WebApi:
    from .auth import token_provider
    env = args.env_url or os.environ.get("DATAVERSE_URL")
    if not env:
        raise SystemExit("set DATAVERSE_URL (e.g. https://<org>.crm4.dynamics.com) or pass --env-url")
    return WebApi(env, token_provider(env))


def cmd_inspect(site, out=print) -> int:
    out(f"{len(site.settings)} Web API table setting group(s), {len(site.other_settings)} other site setting(s), "
        f"{len(site.permissions)} table permission(s), {len(site.roles)} web role(s)")
    for t, s in sorted(site.settings.items()):
        out(f"  Webapi/{t}: enabled={s.enabled} fields={s.fields!r} UseFieldsFromView={s.use_view}")
    for p in site.permissions:
        names = [site.roles[r].name if r in site.roles else r for r in p.role_ids]
        out(f"  permission {p.name!r}: {p.table}, {p.scope}, {'/'.join(sorted(p.privileges)) or 'no privileges'}, "
            f"roles: {', '.join(names) or 'none'}")
    return 0


def report(findings, out=print) -> int:
    for f in findings:
        out(str(f))
    out(lintmod.summary(findings))
    return 1 if any(f.level == "error" for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pagekit", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--env-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "lint", "columns"):
        s = sub.add_parser(name)
        s.add_argument("site_dir")
        if name == "lint":
            s.add_argument("--expect", nargs="?", const=str(EPISODE / "portal.json"),
                           help="portal.json with the expected tables and columns (default file if no value)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.site_dir)
    if not root.is_dir():
        print(f"error: {root} is not a folder")
        return 2
    site = load_site(root)
    try:
        if args.cmd == "inspect":
            return cmd_inspect(site)
        if args.cmd == "lint":
            expected = None
            if args.expect:
                expected = json.loads(Path(args.expect).read_text(encoding="utf-8"))["expected_web_api"]
            return report(lintmod.lint(site, expected))
        if args.cmd == "columns":
            return report(columns.check(make_api(args), site))
    except (DataverseError, ValueError) as e:
        print(f"error: {e}")
        return 1
    return 2
