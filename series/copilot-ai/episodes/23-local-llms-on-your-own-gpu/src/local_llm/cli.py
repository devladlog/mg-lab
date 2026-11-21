"""python -m local_llm probe | models | sizing | bench | extract"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench as bench_mod
from . import extract as extract_mod
from . import sizing
from .http import assert_local
from .ollama import OllamaClient, placement
from .openai_compat import KNOWN_SERVERS, probe


def _client(args) -> OllamaClient:
    if not args.allow_remote:
        assert_local(args.host)
    return OllamaClient(args.host)


def cmd_probe(args) -> int:
    servers = dict(KNOWN_SERVERS)
    for item in args.extra or []:
        name, _, url = item.partition("=")
        servers[name] = url
    if not args.allow_remote:
        for url in servers.values():
            assert_local(url)
    result = probe(servers, timeout=args.timeout)
    for name, r in result.items():
        print(f"{name:10} {'UP  ' if r['up'] else 'down'} {servers[name]}  " + (", ".join(r["models"][:8]) or r["error"]))
    return 0 if any(r["up"] for r in result.values()) else 1


def cmd_models(args) -> int:
    c = _client(args)
    print("On disk (GET /api/tags):")
    for m in c.tags():
        d = m.get("details", {})
        print(f"  {m['name']:32} {m.get('size', 0) / sizing.GIB:6.1f} GiB  {d.get('parameter_size', '?'):>6}  {d.get('quantization_level', '?')}")
    print("In memory (GET /api/ps):")
    for m in c.ps():
        print(f"  {m['name']:32} {placement(m):>16}  context {m.get('context_length', '?')}  size_vram {m.get('size_vram', 0) / sizing.GIB:.1f} GiB")
    return 0


def _vram(args) -> tuple[int, str]:
    if args.vram_gib:
        return int(args.vram_gib * sizing.GIB), "given with --vram-gib"
    gpus = sizing.read_nvidia_smi()
    if not gpus:
        raise SystemExit("no nvidia-smi found: pass --vram-gib")
    g = gpus[0]
    return g["free_bytes"], f"nvidia-smi: {g['name']}, free of {g['total_bytes'] / sizing.GIB:.1f} GiB total"


def cmd_sizing(args) -> int:
    c = _client(args)
    vram, src = _vram(args)
    print(f"VRAM budget {vram / sizing.GIB:.1f} GiB ({src}); margin {args.margin_gib} GiB; KV cache {args.kv_type}")
    tags = {m["name"]: m for m in c.tags()}
    for name in args.models or list(tags):
        if name not in tags:
            print(f"{name}: not on disk (ollama pull {name})")
            continue
        try:
            arch = sizing.ModelArch.from_show(c.show(name))
        except ValueError as e:
            print(f"{name}: cannot size ({e})")
            continue
        w = int(tags[name]["size"])
        print(f"{name}")
        for ctx in args.context:
            print("   " + sizing.estimate(w, arch, ctx, vram, args.kv_type, args.margin_gib).line())
        print(f"   largest context that fits: {sizing.max_context(w, arch, vram, args.kv_type, args.margin_gib)} tokens "
              f"(model limit {arch.max_context})")
    return 0


def cmd_bench(args) -> int:
    c = _client(args)
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    rows = [bench_mod.run_bench(c, m, prompt, args.repeats, args.num_predict, args.num_ctx).row() for m in args.models]
    print(bench_mod.HEADER)
    print("\n".join(rows))
    if not args.keep_loaded:
        for m in args.models:
            c.unload(m)
    return 0


def cmd_extract(args) -> int:
    c = _client(args)
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    email = Path(args.email).read_text(encoding="utf-8")
    obj, errs, res = extract_mod.extract(c, args.model, email, schema, args.num_ctx)
    print(json.dumps(obj, indent=2, ensure_ascii=False) if obj is not None else res.text)
    print(f"-- {res.gen_tokens} tokens, {res.gen_tps:.1f} tok/s, nothing left this machine ({args.host})")
    for e in errs:
        print("schema error:", e)
    if args.expected and obj is not None:
        diffs = extract_mod.compare(obj, json.loads(Path(args.expected).read_text(encoding="utf-8")))
        for d in diffs:
            print("differs:", d)
        print("expected fields: " + ("ALL MATCH" if not diffs else f"{len(diffs)} differ"))
        errs = errs + diffs
    return 1 if errs else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local_llm", description="Local LLM toolkit (Ollama native API + OpenAI-compatible servers)")
    p.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama base URL (default: local)")
    p.add_argument("--allow-remote", action="store_true", help="allow non-local endpoints (off by default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("probe", help="which local OpenAI-compatible servers answer?")
    s.add_argument("--extra", nargs="*", metavar="NAME=URL", help="e.g. foundry=http://127.0.0.1:PORT/v1")
    s.add_argument("--timeout", type=float, default=2.0)
    s.set_defaults(fn=cmd_probe)

    sub.add_parser("models", help="models on disk and in memory").set_defaults(fn=cmd_models)

    s = sub.add_parser("sizing", help="estimate whether models fit in VRAM")
    s.add_argument("models", nargs="*")
    s.add_argument("--context", type=int, nargs="+", default=[4096, 32768])
    s.add_argument("--kv-type", choices=sorted(sizing.KV_FACTOR), default="f16")
    s.add_argument("--vram-gib", type=float)
    s.add_argument("--margin-gib", type=float, default=sizing.DEFAULT_MARGIN_GIB)
    s.set_defaults(fn=cmd_sizing)

    s = sub.add_parser("bench", help="tokens per second from the server's own timings")
    s.add_argument("models", nargs="+")
    s.add_argument("--prompt", default="Explain in about 150 words why a company might run an LLM locally.")
    s.add_argument("--prompt-file")
    s.add_argument("--repeats", type=int, default=3)
    s.add_argument("--num-predict", type=int, default=200)
    s.add_argument("--num-ctx", type=int)
    s.add_argument("--keep-loaded", action="store_true")
    s.set_defaults(fn=cmd_bench)

    s = sub.add_parser("extract", help="schema-constrained extraction from an email, all local")
    s.add_argument("model")
    s.add_argument("--email", required=True)
    s.add_argument("--schema", required=True)
    s.add_argument("--expected")
    s.add_argument("--num-ctx", type=int)
    s.set_defaults(fn=cmd_extract)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ConnectionError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
