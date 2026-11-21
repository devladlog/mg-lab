"""python -m claude_ms triage|fallback|code-env"""
from __future__ import annotations

import argparse
import sys

from .client import ConfigError, build_client
from .claude_code_env import build_env, render
from .fallback import ask_with_fallback
from .triage import load_vendors, run_triage


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude_ms", description="Claude on Microsoft Foundry, Contoso procurement demo")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("triage", help="tool-use loop over the Contoso vendor renewals")
    t.add_argument("--resource")
    t.add_argument("--deployment", required=True, help="Foundry deployment name (the Messages API `model`)")
    t.add_argument("--vendors", default="samples/vendors.json")
    t.add_argument("--question", default="Which contracts renew in the next 180 days and what do they cost? Anything I should act on this week?")

    f = sub.add_parser("fallback", help="ask a question, failing over across deployments")
    f.add_argument("--resource")
    f.add_argument("--deployments", required=True, help="comma separated, tried in order")
    f.add_argument("--prompt", required=True)

    c = sub.add_parser("code-env", help="print the environment that points Claude Code at Foundry")
    c.add_argument("--resource", required=True)
    c.add_argument("--shell", choices=["bash", "powershell"], default="powershell")
    for fam in ("sonnet", "haiku", "opus"):
        c.add_argument(f"--{fam}", help=f"deployment name for the {fam} role")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "code-env":
            models = {f: getattr(args, f) for f in ("sonnet", "haiku", "opus") if getattr(args, f)}
            sys.stdout.write(render(build_env(args.resource, models), args.shell))
            return 0
        client, conn = build_client(args.resource)
        print(f"resource={conn.resource} auth={conn.auth}")
        if args.cmd == "triage":
            res = run_triage(client, args.deployment, args.question, load_vendors(args.vendors), on_event=lambda e: print("  ->", e))
            print(res.text)
            print(f"[turns={res.turns} stop={res.stop_reason} tokens in/out={res.input_tokens}/{res.output_tokens}]")
        else:
            res = ask_with_fallback(client, [d.strip() for d in args.deployments.split(",") if d.strip()], args.prompt)
            for dep, why in res.skipped:
                print(f"  skipped {dep}: {why}")
            print(f"[answered by {res.deployment}]\n{res.text}")
        return 0
    except (ConfigError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
