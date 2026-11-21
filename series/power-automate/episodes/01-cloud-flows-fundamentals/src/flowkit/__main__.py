"""python -m flowkit lint <flow.json>...    |    python -m flowkit run <flow.json> --trigger t.json --mocks m.json"""
import argparse
import json
import sys
from datetime import datetime, timezone

from . import expr
from .lint import load_flow, main as lint_main
from .sim import SimulationError, run_flow


def run_main(argv) -> int:
    p = argparse.ArgumentParser(prog="flowkit run", description="Dry-run a flow with mocked connectors")
    p.add_argument("flow")
    p.add_argument("--trigger", help="JSON file with the trigger body (e.g. a SharePoint item)")
    p.add_argument("--mocks", help="JSON file: {action name: {status, body}}")
    p.add_argument("--now", help="UTC time for utcNow(), e.g. 2026-01-05T09:00:00Z")
    a = p.parse_args(argv)
    body = json.load(open(a.trigger, encoding="utf-8")) if a.trigger else None
    mocks = json.load(open(a.mocks, encoding="utf-8")) if a.mocks else {}
    now = expr.parse_timestamp(a.now) if a.now else datetime.now(timezone.utc)
    try:
        r = run_flow(load_flow(a.flow), body, mocks, now)
    except SimulationError as e:
        print(f"Can't simulate: {e}")
        return 2
    width = max([len(n) for n in r.order] + [6])
    for name in r.order:
        res = r.actions[name]
        line = f"  {name:<{width}}  {res.status}"
        if res.error:
            line += f"  ({res.error})"
        print(line)
    if r.status == "Skipped":
        print("Run: Skipped (trigger condition is false: no run is created)")
    else:
        print(f"Run: {r.status}" + (f"  {r.terminate_error}" if r.terminate_error else ""))
    return 0 if r.status in ("Succeeded", "Skipped") else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("lint", "run"):
        print(__doc__)
        return 2
    return lint_main(argv[1:]) if argv[0] == "lint" else run_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
