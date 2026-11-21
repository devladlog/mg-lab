"""python -m copilot_governance SNAPSHOT.json [--sharing scan.json] [--json] [--fail-on high|medium|never]"""
from __future__ import annotations

import argparse
import json

from .checks import run_checks
from .model import load_snapshot
from .oversharing import analyse, format_sites, load_scan

ICON = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "unknown": "????"}
RANK = {"high": 3, "medium": 2, "low": 1}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilot_governance", description=__doc__)
    p.add_argument("snapshot", help="JSON from scripts/Export-CopilotGovernanceSnapshot.ps1")
    p.add_argument("--sharing", help="JSON from graph_scan.py (item-level sharing links)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on", choices=["high", "medium", "never"], default="high",
                   help="exit 1 when a failed check has at least this severity (default high)")
    args = p.parse_args(argv)

    snap = load_snapshot(args.snapshot)
    findings = run_checks(snap)
    sites = analyse(load_scan(args.sharing)) if args.sharing else None

    if args.json:
        print(json.dumps({"collectedAt": snap.collected_at, "findings": [f.as_dict() for f in findings],
                          "sharing": [{"site": s.site, "scanned": s.items_scanned, "exposed": len(s.exposed)} for s in sites]
                          if sites is not None else None}, indent=2))
    else:
        print(f"Copilot governance posture (snapshot {snap.collected_at or 'undated'})\n")
        for f in findings:
            print(f"[{ICON[f.status]}] {f.id} {f.title} ({f.severity})")
            print(f"       {f.detail}")
            if f.status in ("fail", "warn") and f.fix:
                print(f"       fix: {f.fix}")
            for item in f.items[:5]:
                print(f"       - {item}")
        counts = {k: sum(1 for f in findings if f.status == k) for k in ICON}
        print("\n" + ", ".join(f"{v} {k}" for k, v in counts.items()))
        if sites is not None:
            print("\n" + format_sites(sites))

    if args.fail_on == "never":
        return 0
    threshold = RANK[args.fail_on]
    return 1 if any(f.status == "fail" and RANK[f.severity] >= threshold for f in findings) else 0
