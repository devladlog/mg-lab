from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .dataset import analyse, load_live, load_sample
from .dataverse import DataverseClient, DataverseError, mask_org_url

ORDER = {"error": 0, "warning": 1, "info": 2}


def render_text(findings, summary, source: str) -> str:
    lines = [f"source: {source}",
             f"{summary['opportunities']} opportunities, {summary['accounts']} accounts, {summary['cases']} cases, "
             f"{summary['articles']} knowledge articles "
             f"({summary['articles_usable_for_ui_language']} usable for UI language {summary['ui_localeid']})"]
    for f in sorted(findings, key=lambda x: (ORDER[x.severity], x.entity, x.record, x.code)):
        lines.append(f"{f.severity.upper():7} {f.code}  {f.entity} '{f.record}': {f.message}")
    lines.append(f"-- {summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="d365_copilot_ready", description=__doc__ or "Dynamics 365 Copilot readiness check")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="read opportunities, accounts, cases and knowledge articles and report what Copilot cannot use")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", metavar="DIR", help="folder with <entity set>.json files in Web API shape")
    src.add_argument("--org", metavar="URL", help="Dataverse environment URL, https://<org>.crm4.dynamics.com")
    c.add_argument("--token-env", default="DATAVERSE_TOKEN", help="environment variable holding a bearer token (live mode)")
    c.add_argument("--page-size", type=int, default=500)
    c.add_argument("--ui-language", type=int, default=1033, help="LCID of the representative's UI language (default 1033, English)")
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.add_argument("--fail-on", choices=["error", "warning", "never"], default="error")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.sample:
            ds, source = load_sample(args.sample), f"sample files in {args.sample}"
        else:
            token = os.environ.get(args.token_env, "")
            if not token:
                print(f"error: set {args.token_env} to a Dataverse access token (the tool never asks for credentials)", file=sys.stderr)
                return 2
            client = DataverseClient(args.org, token, args.page_size)
            ds, source = load_live(client), f"live {mask_org_url(args.org)}"
    except (DataverseError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    findings, summary = analyse(ds, args.ui_language)
    if args.format == "json":
        print(json.dumps({"source": source, "summary": summary, "findings": [f.as_dict() for f in findings]}, indent=2))
    else:
        print(render_text(findings, summary, source))
    if args.fail_on == "never":
        return 0
    bad = summary["errors"] + (summary["warnings"] if args.fail_on == "warning" else 0)
    return 1 if bad else 0
