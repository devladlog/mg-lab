#!/usr/bin/env python3
"""Run the golden set against a model route and score it. Never fakes output: `run` needs a real endpoint.

  python evaluate.py score  --golden golden.jsonl --answers answers.jsonl        # offline: score answers you already have
  python evaluate.py run --route foundry --endpoint https://<name>.openai.azure.com --model <deployment> --token-env AZURE_TOKEN
  python evaluate.py run --route claude  --model <model id> --key-env ANTHROPIC_API_KEY [--base-url https://api.anthropic.com]
  python evaluate.py run --route openai-compatible --endpoint http://127.0.0.1:8099 --model mock      # local mock server in the tests

Secrets are read from environment variables you name; they are never accepted on the command line and never printed.
answers.jsonl lines: {"id": "g01", "text": "<the model's raw text>"}  (AI Builder: copy the prompt output into it by hand).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import triage

HERE = Path(__file__).resolve().parent


def post(url, headers, body, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"content-type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def call(route, a, notes):
    if route == "claude":
        key = os.environ.get(a.key_env or "")
        if not key:
            raise SystemExit(f"environment variable {a.key_env!r} is empty: export it first (type it off camera)")
        resp = post(f"{(a.base_url or 'https://api.anthropic.com').rstrip('/')}/v1/messages",
                    {"x-api-key": key, "anthropic-version": a.anthropic_version}, triage.anthropic_body(a.model, notes))
        return triage.anthropic_text(resp), triage.usage(resp)
    headers = {}
    if route == "foundry":
        tok = os.environ.get(a.token_env or "")
        if not tok:
            raise SystemExit(f"environment variable {a.token_env!r} is empty: get a token with the az CLI on the lab laptop, see demo.md")
        headers["authorization"] = f"Bearer {tok}"
    resp = post(f"{a.endpoint.rstrip('/')}/openai/v1/chat/completions", headers, triage.openai_body(a.model, notes))
    return triage.openai_text(resp), triage.usage(resp)


def cmd_score(a):
    golden = triage.load_golden(a.golden)
    answers = {}
    for line in Path(a.answers).read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            answers[o["id"]] = o.get("text")
    print(json.dumps(triage.score(golden, answers), indent=2))
    return 0


def cmd_run(a):
    golden = triage.load_golden(a.golden)
    answers, tin, tout, lat = {}, 0, 0, []
    for g in golden:
        t0 = time.time()
        try:
            text, (i, o) = call(a.route, a, g["notes"])
        except urllib.error.URLError as e:
            text, i, o = None, 0, 0
            print(f"{g['id']}: request failed: {e}", file=sys.stderr)
        lat.append(time.time() - t0)
        answers[g["id"]] = text
        tin, tout = tin + i, tout + o
    res = triage.score(golden, answers)
    res.update({"route": a.route, "model": a.model, "tokens_in": tin, "tokens_out": tout, "median_seconds": round(sorted(lat)[len(lat) // 2], 2) if lat else 0})
    if a.price_in is not None and a.price_out is not None:
        res["estimated_cost_usd"] = round((tin * a.price_in + tout * a.price_out) / 1e6, 6)
    print(json.dumps(res, indent=2))
    if a.save:
        Path(a.save).write_text("".join(json.dumps({"id": k, "text": v}) + "\n" for k, v in answers.items()), encoding="utf-8")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--golden", default=str(HERE / "golden.jsonl"))
    s.add_argument("--answers", required=True)
    r = sub.add_parser("run")
    r.add_argument("--route", choices=["foundry", "claude", "openai-compatible"], required=True)
    r.add_argument("--golden", default=str(HERE / "golden.jsonl"))
    r.add_argument("--endpoint")
    r.add_argument("--base-url")
    r.add_argument("--model", required=True)
    r.add_argument("--token-env")
    r.add_argument("--key-env")
    r.add_argument("--anthropic-version", default=triage.ANTHROPIC_VERSION)
    r.add_argument("--price-in", type=float, help="USD per million input tokens, from the provider's price page on the day")
    r.add_argument("--price-out", type=float, help="USD per million output tokens")
    r.add_argument("--save")
    a = ap.parse_args(argv)
    if a.cmd == "run" and a.route != "claude" and not a.endpoint:
        ap.error("--endpoint is required for this route")
    return cmd_score(a) if a.cmd == "score" else cmd_run(a)


if __name__ == "__main__":
    raise SystemExit(main())
