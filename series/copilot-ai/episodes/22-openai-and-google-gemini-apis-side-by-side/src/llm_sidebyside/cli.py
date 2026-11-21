"""python -m llm_sidebyside payloads | schema | run {extract,tool,truncate} [--vendor openai|gemini|both]"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import contract, dialects, gemini_adapter, openai_adapter
from .errors import Failure, RunError
from .models import estimate_cost_usd, load_prices

HERE = os.path.dirname(os.path.dirname(__file__))
SAMPLES = os.path.join(HERE, "samples")
TASKS = ("extract", "tool", "truncate")


def _payloads(args) -> dict:
    om, gm = args.openai_model, args.gemini_model
    return {
        "extract": {
            "openai": dialects.openai_request(om, contract.SYSTEM, contract.EXTRACT_PROMPT, schema=contract.EXTRACT_SCHEMA),
            "gemini": dialects.gemini_request(gm, contract.SYSTEM, contract.EXTRACT_PROMPT, schema=contract.EXTRACT_SCHEMA),
        },
        "tool": {
            "openai": dialects.openai_request(om, contract.SYSTEM, contract.TOOL_PROMPT, tool=contract.TOOL_SPEC),
            "gemini": dialects.gemini_request(gm, contract.SYSTEM, contract.TOOL_PROMPT, tool=contract.TOOL_SPEC),
        },
        "truncate": {
            "openai": dialects.openai_request(om, contract.SYSTEM, contract.TRUNCATE_PROMPT, max_output_tokens=contract.TRUNCATE_MAX_TOKENS),
            "gemini": dialects.gemini_request(gm, contract.SYSTEM, contract.TRUNCATE_PROMPT, max_output_tokens=contract.TRUNCATE_MAX_TOKENS),
        },
    }


def cmd_payloads(args) -> int:
    all_ = _payloads(args)
    print(json.dumps(all_[args.task] if args.task else all_, indent=2, ensure_ascii=False))
    return 0


def cmd_schema(args) -> int:
    strict, report = dialects.to_openai_strict(contract.EXTRACT_SCHEMA)
    print("OpenAI strict conversion")
    print(f"  made nullable (optional in canonical): {', '.join(report['made_nullable']) or '-'}")
    print(f"  dropped (not in the strict subset):    {', '.join(f'{p}:{k}' for p, k in report['dropped_keywords']) or '-'}")
    print(f"  objects closed with additionalProperties false: {len(report['closed_objects'])}")
    print("Gemini")
    print(f"  accepted but not enforced:             {', '.join(f'{p}:{k}' for p, k in dialects.gemini_unenforced(contract.EXTRACT_SCHEMA)) or '-'}")
    if args.json:
        print(json.dumps(strict, indent=2))
    return 0


def _runner(vendor: str, args):
    if vendor == "openai":
        client = openai_adapter.build_client(base_url=args.openai_base_url)
        return client, openai_adapter, args.openai_model
    return gemini_adapter.build_client(), gemini_adapter, args.gemini_model


def cmd_run(args) -> int:
    data = contract.load_vendors(args.vendors)
    prices = load_prices(args.prices)
    vendors = ("openai", "gemini") if args.vendor == "both" else (args.vendor,)
    rc = 0
    for v in vendors:
        client, mod, model = _runner(v, args)
        try:
            if args.task == "extract":
                out = mod.run_extract(client, model)
            elif args.task == "truncate":
                out = mod.run_truncate(client, model)
            else:
                out = mod.run_tool(client, model, data)
        except Failure as f:
            print(f"[{v}] FAILED {f}")
            rc = 1
            continue
        cost = estimate_cost_usd(out, prices)
        u = out.usage
        print(f"[{v}] {out.model} status={out.status} requests={out.requests} "
              f"in={u.input_tokens} out={u.output_tokens} reasoning={u.reasoning_tokens} cached={u.cached_tokens} "
              f"cost~{'n/a' if cost is None else f'${cost:.5f}'}")
        if out.tool_calls:
            print(f"    tool calls: {', '.join(out.tool_calls)}")
        print("    " + (out.text or "(no text)").replace("\n", "\n    "))
        for p in out.problems:
            print(f"    PROBLEM {p}")
        rc = rc or (0 if out.ok or out.status == "truncated" and args.task == "truncate" else 1)
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm_sidebyside", description=__doc__)
    p.add_argument("--openai-model", default=os.environ.get("OPENAI_MODEL", openai_adapter.DEFAULT_MODEL))
    p.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", gemini_adapter.DEFAULT_MODEL))
    sub = p.add_subparsers(dest="command", required=True)
    sp = sub.add_parser("payloads", help="print the request bodies, no network")
    sp.add_argument("task", nargs="?", choices=TASKS)
    sp.set_defaults(fn=cmd_payloads)
    ss = sub.add_parser("schema", help="show how the canonical schema is converted, no network")
    ss.add_argument("--json", action="store_true")
    ss.set_defaults(fn=cmd_schema)
    sr = sub.add_parser("run", help="call the real APIs (needs your own keys, costs money)")
    sr.add_argument("task", choices=TASKS)
    sr.add_argument("--vendor", choices=("openai", "gemini", "both"), default="both")
    sr.add_argument("--vendors", default=os.path.join(SAMPLES, "vendors.json"))
    sr.add_argument("--prices", default=os.path.join(SAMPLES, "prices.json"))
    sr.add_argument("--openai-base-url", default=os.environ.get("OPENAI_BASE_URL"),
                    help="e.g. https://<resource>.openai.azure.com/openai/v1/ for Azure OpenAI")
    sr.set_defaults(fn=cmd_run)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
