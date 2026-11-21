"""python -m flowkit lint <flow.json>...
python -m flowkit run <flow.json> --trigger t.json --mocks m.json [--now ...]
python -m flowkit eval "<expression>" [--now 2026-07-13T06:00:00Z] [--var name=json ...]"""
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
    p.add_argument("--params", help="JSON file: {parameter name: value} (e.g. environment variables)")
    a = p.parse_args(argv)
    params = json.load(open(a.params, encoding="utf-8")) if a.params else None
    body = json.load(open(a.trigger, encoding="utf-8")) if a.trigger else None
    mocks = json.load(open(a.mocks, encoding="utf-8")) if a.mocks else {}
    now = expr.parse_timestamp(a.now) if a.now else datetime.now(timezone.utc)
    try:
        r = run_flow(load_flow(a.flow), body, mocks, now, parameters=params)
    except SimulationError as e:
        print(f"Can't simulate: {e}")
        return 2
    width = max([len(n) for n in r.order] + [6])
    for name in dict.fromkeys(r.order):  # loop iterations: show each action once, with its last result
        res = r.actions[name]
        line = f"  {name:<{width}}  {res.status}"
        if res.iterations:
            line += f"  ({res.iterations} iterations)"
        if res.error:
            line += f"  ({res.error})"
        print(line)
    retried = [(n, res) for n, res in r.history if len(res.attempts) > 1]
    for n, res in retried:
        print(f"  retried {n}: " + ", ".join(f"{s}" + (f" (waited {w:g}s)" if w is not None else "") for s, w in res.attempts))
    if r.status == "Skipped":
        print("Run: Skipped (trigger condition is false: no run is created)")
    else:
        print(f"Run: {r.status}" + (f"  {r.terminate_error}" if r.terminate_error else ""))
    return 0 if r.status in ("Succeeded", "Skipped") else 1


def eval_main(argv) -> int:
    p = argparse.ArgumentParser(prog="flowkit eval", description="Evaluate one expression locally")
    p.add_argument("expression")
    p.add_argument("--now", help="UTC time for utcNow()")
    p.add_argument("--var", action="append", default=[], help="name=<json> made available as variables('name')")
    a = p.parse_args(argv)
    now = expr.parse_timestamp(a.now) if a.now else datetime.now(timezone.utc)
    variables = {}
    for v in a.var:
        name, _, raw = v.partition("=")
        variables[name] = json.loads(raw)
    try:
        value = expr.evaluate(a.expression, expr.Context(now=now, variables=variables))
    except expr.ExpressionError as e:
        print(f"InvalidTemplate: {e}")
        return 1
    print(json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    commands = {"lint": lint_main, "run": run_main, "eval": eval_main}
    if not argv or argv[0] not in commands:
        print(__doc__)
        return 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
