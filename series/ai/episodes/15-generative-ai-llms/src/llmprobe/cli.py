"""python -m llmprobe tokens | probe | sample | stream | budget

tokens                   offline: the same sentences in English and Portuguese, two encodings
probe / sample / stream  real calls to an Azure OpenAI deployment (non-reasoning model)
budget                   plan the window, drop chunks that do not fit, then compare the estimate with the billed tokens
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import budget as bd
from . import probe, sampling, stream, tokens
from .client import make_client
from .guards import ModelError, ensure_sampling_model

DATA = Path(__file__).resolve().parents[2] / "data"


def _common(p):
    p.add_argument("--endpoint", default=os.environ.get("LLMPROBE_ENDPOINT"), help="https://<name>.openai.azure.com")
    p.add_argument("--deployment", default="chat", help="deployment name (the 'model' field of the request)")
    p.add_argument("--model", default="gpt-4.1-mini", help="the model behind the deployment (decides which parameters are allowed)")
    p.add_argument("--allow-unverified-model", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="llmprobe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tokens", help="offline: token counts, English versus Portuguese")
    t.add_argument("--pairs", default=str(DATA / "pairs.json"))
    t.add_argument("--show", metavar="TEXT", help="print the token pieces of one text")
    t.add_argument("--encoding", default="o200k_base", choices=list(tokens.ENCODINGS))
    p = sub.add_parser("probe", help="next-token probabilities, with and without the handbook")
    _common(p)
    p.add_argument("--cases", default=str(DATA / "probe.json"))
    p.add_argument("--context", default=str(DATA / "handbook_leave.md"))
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--threshold", type=float, default=0.9)
    s = sub.add_parser("sample", help="same prompt N times per setting: wording versus facts; exit 1 if a fact is lost")
    _common(s)
    s.add_argument("--spec", default=str(DATA / "sampling.json"))
    s.add_argument("--context", default=str(DATA / "handbook_leave.md"))
    s.add_argument("--runs", type=int, default=8)
    s.add_argument("--min-fact-rate", type=float, default=1.0)
    s.add_argument("--show", action="store_true", help="print every answer")
    m = sub.add_parser("stream", help="time to first content, streaming versus blocking")
    _common(m)
    m.add_argument("--runs", type=int, default=3)
    m.add_argument("--max-output", type=int, default=300)
    m.add_argument("--question", default="Explain, step by step, how an employee requests annual leave and what happens next.")
    b = sub.add_parser("budget", help="plan the window, fit chunks, compare the estimate with the billed prompt tokens")
    _common(b)
    b.add_argument("--file", default=str(DATA / "handbook_leave.md"))
    b.add_argument("--question", default="How many days can I carry over, and until when?")
    b.add_argument("--window", type=int, default=bd.STANDARD_CONTEXT)
    b.add_argument("--max-output", type=int, default=300)
    b.add_argument("--context-budget", type=int, default=None, help="tokens for retrieved text (default: whatever the plan leaves)")
    b.add_argument("--dry-run", action="store_true", help="plan only, no model call")
    return ap


def _client(a):
    ensure_sampling_model(a.model, a.allow_unverified_model)
    if not a.endpoint:
        raise SystemExit("--endpoint or LLMPROBE_ENDPOINT is required")
    return make_client(a.endpoint)


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return _run(a)
    except (ModelError, bd.BudgetError, probe.ProbeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _run(a) -> int:
    if a.cmd == "tokens":
        if a.show:
            ps = tokens.pieces(a.show, a.encoding)
            print(f"{a.encoding}: {len(ps)} tokens")
            print(" | ".join(repr(x) for x in ps))
            return 0
        print(tokens.render(tokens.compare(tokens.load_pairs(a.pairs))))
        return 0
    if a.cmd == "budget" and a.dry_run:
        return _budget(a, None)
    c = _client(a)
    if a.cmd == "probe":
        cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))
        rows = probe.run_cases(c, a.deployment, cases, Path(a.context).read_text(encoding="utf-8"), a.top, a.threshold)
        print(probe.render(rows, a.threshold))
        for r in rows:
            print(f"  {r['id']:<8}{'ctx' if r['context'] else '   '} " + "  ".join(f"{t}={p:.3f}" for t, p in r["candidates"]))
        return 0
    if a.cmd == "sample":
        spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
        ctx = Path(a.context).read_text(encoding="utf-8")
        msgs = [{"role": "system", "content": spec["system"]},
                {"role": "user", "content": f"<<CONTEXT>>\n{ctx.strip()}\n<<END>>\n\n{spec['question']}"}]
        results = [sampling.run_setting(c, a.deployment, msgs, s, a.runs) for s in sampling.DEFAULT_SETTINGS]
        sums = [sampling.summarise(r, spec["facts"]) for r in results]
        print(sampling.render(sums))
        if a.show:
            for r in results:
                print(f"\n== {r['setting'].label}")
                for o in r["outputs"]:
                    print(f"- {o}")
        why = sampling.failing(sums, a.min_fact_rate)
        for w in why:
            print(f"FAIL {w}")
        return 1 if why else 0
    if a.cmd == "stream":
        msgs = [{"role": "system", "content": "You are the Contoso HR assistant. Be concise and concrete."},
                {"role": "user", "content": a.question}]
        runs = [stream.stream_once(c, a.deployment, msgs, a.max_output) for _ in range(a.runs)]
        block = [stream.blocking_once(c, a.deployment, msgs, a.max_output) for _ in range(a.runs)]
        print(stream.render(stream.summarise(runs, block)))
        print(f"first run: {runs[0].chunks} chunks in total, {runs[0].content_chunks} with text, "
              f"finish_reason={runs[0].finish_reason}")
        return 0
    return _budget(a, c)


def _budget(a, c) -> int:
    enc = tokens.encoding_name_for(a.model)
    system = "You are the Contoso HR assistant. Use only the reference text between <<CONTEXT>> and <<END>>."
    fixed = tokens.count(system, enc) + tokens.count(a.question, enc)
    plan = bd.make_plan(a.window, a.max_output, fixed)
    ctx_budget = min(plan.available, a.context_budget) if a.context_budget is not None else plan.available
    chunks = bd.split_sections(Path(a.file).read_text(encoding="utf-8"))
    kept, dropped = bd.fit_chunks(chunks, ctx_budget, enc)
    print(f"encoding {enc} (tiktoken's mapping for {a.model})")
    print(f"window {plan.window:,} = output reserve {plan.reserve_output:,} + system/question {plan.fixed_tokens:,} "
          f"+ available {plan.available:,}; context budget used {ctx_budget:,}")
    print(f"chunks kept {len(kept)} ({sum(tokens.count(k, enc) for k in kept):,} tokens), dropped {len(dropped)}")
    for d in dropped:
        print(f"  dropped: {d.splitlines()[0]}")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": "<<CONTEXT>>\n" + "\n\n".join(kept) + f"\n<<END>>\n\n{a.question}"}]
    est = bd.content_tokens(messages, enc)
    bd.check_request(a.window, est, a.max_output)
    print(f"estimated prompt tokens (message text only): {est:,}")
    if a.dry_run:
        return 0
    r = c.chat.completions.create(model=a.deployment, messages=messages, temperature=0, max_completion_tokens=a.max_output)
    billed = r.usage.prompt_tokens
    print(f"billed prompt tokens: {billed:,}  (estimate is {billed - est:+d} off: chat-format overhead and encoding differences)")
    print(f"completion tokens: {r.usage.completion_tokens:,}  finish_reason={r.choices[0].finish_reason}")
    print(f"answer: {(r.choices[0].message.content or '').strip()}")
    return 0
