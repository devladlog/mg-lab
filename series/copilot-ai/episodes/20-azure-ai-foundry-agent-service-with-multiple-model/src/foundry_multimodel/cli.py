"""python -m foundry_multimodel run|report|plan ...

  run     live: creates one prompt agent per model in YOUR Foundry project, asks every task, deletes the agents
  plan    prints how many requests a run would send (no network)
  report  renders a results.json (or recomputes routes with another --min-score)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .runner import format_report, load_config, load_tasks, planned_requests, run


def main(argv: list[str] | None = None, backend=None) -> int:
    p = argparse.ArgumentParser(prog="foundry_multimodel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "plan"):
        s = sub.add_parser(name)
        s.add_argument("--config", required=True)
        s.add_argument("--tasks", required=True)
        s.add_argument("--max-requests", type=int, default=200)
    sub.choices["run"].add_argument("--out", required=True)
    sub.choices["run"].add_argument("--keep-agents", action="store_true", help="do not delete the agents afterwards")
    sub.choices["run"].add_argument("--min-score", type=float, default=0.9)
    r = sub.add_parser("report")
    r.add_argument("results")
    r.add_argument("--min-score", type=float, default=0.9)
    args = p.parse_args(argv)

    if args.cmd == "report":
        print(format_report(json.loads(Path(args.results).read_text(encoding="utf-8")), args.min_score))
        return 0

    cfg, tasks = load_config(args.config), load_tasks(args.tasks)
    n = planned_requests(cfg, tasks)
    if args.cmd == "plan":
        print(f"{len(cfg.models)} model(s) x {len(tasks)} task(s) x {cfg.repeats} repeat(s) = {n} request(s); "
              f"{len(cfg.models)} agent(s) created and deleted. Limit --max-requests {args.max_requests}.")
        return 0 if n <= args.max_requests else 2

    if backend is None:
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        if not endpoint:
            print("Set FOUNDRY_PROJECT_ENDPOINT (https://<resource>.services.ai.azure.com/api/projects/<project>) and sign in "
                  "with a credential DefaultAzureCredential can use.", file=sys.stderr)
            return 2
        from .backend import FoundryBackend
        backend = FoundryBackend.from_endpoint(endpoint)
    try:
        result = run(cfg, tasks, backend, max_requests=args.max_requests, keep_agents=args.keep_agents)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(format_report(result, args.min_score))
    return 1 if result["setupErrors"] and not result["rows"] else 0
