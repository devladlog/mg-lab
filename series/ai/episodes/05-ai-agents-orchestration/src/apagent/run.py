"""CLI: work the review queue with the AP assistant; a person answers every approval request.

    PYTHONPATH=src python -m apagent.run --endpoint $AOAI --deployment chat --audit audit/run.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .agent import build_agent, make_client, run_with_approvals
from .audit import AuditTrail
from .store import DATA, InvoiceStore, load_policy

DEFAULT_PROMPT = "Work through the review queue. Approve what the policy allows and tell me what happens to the rest."


def ask_human(stream_in=None, stream_out=None):
    def decide(tool: str, args: dict) -> bool:
        nonlocal stream_in, stream_out
        stream_in, stream_out = stream_in or sys.stdin, stream_out or sys.stdout
        print(f"\n>>> APPROVAL NEEDED  {tool}", file=stream_out)
        for k, v in args.items():
            print(f"    {k}: {v}", file=stream_out)
        print("    Approve? [y/N] ", end="", file=stream_out, flush=True)
        answer = stream_in.readline().strip().lower()
        return answer in ("y", "yes")
    return decide


def fixed(answer: bool):
    def decide(tool: str, args: dict) -> bool:
        print(f">>> {tool} {json.dumps(args)} -> {'approved' if answer else 'declined'} (--approve flag)")
        return answer
    return decide


def report(outcome, audit: AuditTrail, store: InvoiceStore, out=None) -> None:
    out = out or sys.stdout
    print("\n=== Agent ===", file=out)
    print(outcome.response.text, file=out)
    print("\n=== Tool calls (audit) ===", file=out)
    for r in audit.records:
        args = ", ".join(f"{k}={v}" for k, v in (r["arguments"] or {}).items())
        print(f"{r['tool']:<18} {r['outcome']:<8} {r['ms']:>7} ms  {args[:70]}", file=out)
    print("\n=== Queue after the run ===", file=out)
    for inv in store.invoices.values():
        print(f"{inv['id']:<15} {inv['vendor']:<26} {inv['total']:>9} {inv['status']}", file=out)
    u = outcome.usage
    print(f"\ntokens in: {u['input']}  out: {u['output']}"
          f"  approvals asked: {len(outcome.decisions)}", file=out)


async def main_async(argv=None, *, client=None, stdin=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--endpoint", help="https://<resource>.openai.azure.com")
    ap.add_argument("--deployment", default="chat")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--approve", choices=["ask", "all", "none"], default="ask",
                    help="ask (default) prompts on stdin; all/none answer every request (tests, dry runs)")
    ap.add_argument("--data", default=str(DATA / "invoices.json"))
    ap.add_argument("--policy", default=str(DATA / "policy.md"))
    ap.add_argument("--audit", help="append audit records (JSON lines) to this file")
    a = ap.parse_args(argv)
    if client is None:
        if not a.endpoint:
            ap.error("--endpoint is required")
        client = make_client(a.endpoint, a.deployment)

    store, policy, audit = InvoiceStore.load(a.data), load_policy(a.policy), AuditTrail(a.audit)
    agent = build_agent(client, store, policy, audit)
    decide = ask_human(stdin) if a.approve == "ask" else fixed(a.approve == "all")
    outcome = await run_with_approvals(agent, a.prompt, decide)
    report(outcome, audit, store)
    return 0


def main(argv=None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
