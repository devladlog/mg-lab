"""python -m agentfiles inventory | triage-template | plan | skill-lint"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import inventory, plan, skilllint


def _today(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agentfiles", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inventory", help="summarise the search export of .agent files")
    i.add_argument("export", type=Path)
    i.add_argument("--today")
    i.add_argument("--stale-days", type=int, default=plan.STALE_DAYS)
    i.add_argument("--json", action="store_true")

    t = sub.add_parser("triage-template", help="write the sheet the site owners fill in (role, audience, ...)")
    t.add_argument("export", type=Path)
    t.add_argument("--out", type=Path, required=True)

    pl = sub.add_parser("plan", help="upgrade plan per .agent file (Learn's table of upgrade paths)")
    pl.add_argument("export", type=Path)
    pl.add_argument("--triage", type=Path)
    pl.add_argument("--today")
    pl.add_argument("--high-views", type=int, default=plan.HIGH_VIEWS)
    pl.add_argument("--stale-days", type=int, default=plan.STALE_DAYS)
    pl.add_argument("--format", choices=["md", "csv"], default="md")

    s = sub.add_parser("skill-lint", help="check a SKILL.md before uploading it as a site skill")
    s.add_argument("skill", type=Path)

    a = p.parse_args(argv)

    if a.cmd == "skill-lint":
        findings = skilllint.lint_file(a.skill)
        for f in findings:
            print(f"[{f.level.upper()}] {f.rule}: {f.message} ({f.source})")
        errors = sum(1 for f in findings if f.level == "error")
        print(f"Result: {errors} error(s), {len(findings) - errors} warning(s) -> {'FAIL' if errors else 'OK'}")
        return 1 if errors else 0

    files, skipped = inventory.read_inventory(a.export)
    if a.cmd == "inventory":
        summary = inventory.summarize(files, _today(a.today), a.stale_days)
        summary["rows_skipped_not_agent"] = skipped
        if a.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f".agent files: {summary['agent_files']} on {summary['sites']} site(s)")
            for site, n in summary["top_sites"]:
                print(f"  {n:3d}  {site}")
            print(f"never viewed: {summary['never_viewed']}   no owner: {summary['no_owner']}   "
                  f"not modified for {a.stale_days}+ days: {summary['not_modified_for_days']['count']}")
        return 0
    if a.cmd == "triage-template":
        plan.write_triage_template(files, a.out)
        print(f"Wrote {len(files)} row(s) to {a.out}")
        return 0
    triage = plan.read_triage(a.triage) if a.triage else {}
    items = plan.build_plan(files, triage, _today(a.today), a.high_views, a.stale_days)
    if a.format == "csv":
        plan.render_csv(items, sys.stdout)
    else:
        print(plan.render_markdown(items, _today(a.today)))
    return 0
