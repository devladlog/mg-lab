"""python -m customcheck check|explain|convert-prompt"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .convert import prompt_to_skill
from .rules import check_repo, explain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="customcheck", description="Lint Copilot customization files")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="lint .github instructions, prompts, skills and agents")
    p_check.add_argument("root", nargs="?", default=".", type=Path)
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--strict", action="store_true", help="warnings also fail")

    p_explain = sub.add_parser("explain", help="which instruction files apply to a file")
    p_explain.add_argument("root", type=Path)
    p_explain.add_argument("file", help="path relative to root, with /")

    p_conv = sub.add_parser("convert-prompt", help="convert a .prompt.md file to a skill")
    p_conv.add_argument("prompt", type=Path)
    p_conv.add_argument("--skills-dir", type=Path, default=None, help="default: <repo>/.github/skills")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        report = check_repo(args.root)
        if args.json:
            print(json.dumps([f.__dict__ for f in report.findings], indent=2))
        else:
            for f in report.findings:
                print(f.line())
            print(f"{report.count('error')} error(s), {report.count('warn')} warning(s), {report.count('info')} note(s)")
        failed = report.count("error") or (args.strict and report.count("warn"))
        return 1 if failed else 0

    if args.cmd == "explain":
        hits = explain(args.root, args.file)
        print(f"Instruction files that apply to {args.file}:")
        for h in hits or ["(none)"]:
            print(f"  {h}")
        return 0

    skills_dir = args.skills_dir or args.prompt.resolve().parents[1] / "skills"
    try:
        result = prompt_to_skill(args.prompt, skills_dir)
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {result.skill_file}")
    for note in result.notes:
        print(f"  check: {note}")
    return 0
