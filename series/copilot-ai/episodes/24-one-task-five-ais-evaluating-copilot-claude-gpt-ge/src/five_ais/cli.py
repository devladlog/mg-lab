"""python -m five_ais plan | prompts | run | blind | unblind | report"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import blind, runner


def _load(args):
    cfg = runner.load_config(Path(args.config))
    tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    return cfg, tasks, Path(args.config).resolve().parent


def cmd_plan(args) -> int:
    cfg, tasks, base = _load(args)
    provs = runner.build_providers(cfg, args.only, base_dir=base)
    print("\n".join(runner.plan(cfg, tasks, provs, args.repeats or cfg.get("repeats", 1))))
    return 0


def cmd_prompts(args) -> int:
    """Print the exact text each AI receives, and write the empty answer file for the manual provider (Copilot Chat)."""
    cfg, tasks, _ = _load(args)
    template = {}
    for t in tasks:
        system, user = runner.prompt_for(cfg, t)
        text = user if system is None else f"{system}\n\n{user}"      # Copilot Chat gets everything inline
        print(f"===== {t['id']} ({t.get('category', '')}) =====\n{text}\n")
        template[t["id"]] = ""
    if args.write_template:
        Path(args.write_template).write_text(json.dumps(template, indent=2), encoding="utf-8")
        print(f"wrote {args.write_template}: paste each Copilot answer into it, unedited", file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    cfg, tasks, base = _load(args)
    provs = runner.build_providers(cfg, args.only, base_dir=base)
    bad = [(p.id, p.problems()) for p in provs if p.problems()]
    if bad and not args.skip_problems:
        for pid, issues in bad:
            print(f"{pid}: {'; '.join(issues)}", file=sys.stderr)
        print("fix the config/environment, or pass --skip-problems to run the others", file=sys.stderr)
        return 2
    provs = [p for p in provs if not p.problems()]
    print("\n".join(runner.plan(cfg, tasks, provs, args.repeats or cfg.get("repeats", 1))))
    res = runner.run(cfg, tasks, provs, args.repeats or cfg.get("repeats", 1), args.allow_code_exec,
                     progress=lambda r: print(f"  {r['provider']:10} {r['task']:20} {r['score']:.2f} {r['error'] or ''}"))
    Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}\n\n" + runner.report(res))
    return 0


def cmd_blind(args) -> int:
    res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    sheet, key = blind.make_sheet(res, args.seed)
    Path(args.sheet).write_text(sheet, encoding="utf-8")
    Path(args.key).write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"wrote {args.sheet} (review this) and {args.key} (do NOT open it until you have scored)")
    return 0


def cmd_unblind(args) -> int:
    res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    res = blind.unblind(res, json.loads(Path(args.key).read_text(encoding="utf-8")),
                        json.loads(Path(args.scores).read_text(encoding="utf-8")))
    Path(args.results).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(runner.report(res))
    return 0


def cmd_report(args) -> int:
    print(runner.report(json.loads(Path(args.results).read_text(encoding="utf-8"))))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="five_ais", description="One task, five AIs: evaluation harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s, tasks=True):
        s.add_argument("--config", required=True)
        if tasks:
            s.add_argument("--tasks", required=True)

    s = sub.add_parser("plan")
    common(s)
    s.add_argument("--only", nargs="*")
    s.add_argument("--repeats", type=int)
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("prompts", help="print the exact prompts; write the manual answers template")
    common(s)
    s.add_argument("--write-template")
    s.set_defaults(fn=cmd_prompts)

    s = sub.add_parser("run")
    common(s)
    s.add_argument("--only", nargs="*")
    s.add_argument("--repeats", type=int)
    s.add_argument("--out", default="results.json")
    s.add_argument("--allow-code-exec", action="store_true", help="run model-written Python in the restricted runner (see README)")
    s.add_argument("--skip-problems", action="store_true")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("blind")
    s.add_argument("results")
    s.add_argument("--sheet", default="review-sheet.md")
    s.add_argument("--key", default="review-key.json")
    s.add_argument("--seed", type=int, default=20261121)
    s.set_defaults(fn=cmd_blind)

    s = sub.add_parser("unblind")
    s.add_argument("results")
    s.add_argument("--key", required=True)
    s.add_argument("--scores", required=True)
    s.set_defaults(fn=cmd_unblind)

    s = sub.add_parser("report")
    s.add_argument("results")
    s.set_defaults(fn=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
