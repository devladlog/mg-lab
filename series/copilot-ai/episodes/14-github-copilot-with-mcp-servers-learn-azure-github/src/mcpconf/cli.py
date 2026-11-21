"""python -m mcpconf check|convert"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import check, load, to_native


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcpconf", description="Check and convert MCP config files for Copilot in VS Code")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="lint one mcp.json / .mcp.json")
    c.add_argument("file", type=Path)
    c.add_argument("--strict", action="store_true", help="warnings also fail")
    v = sub.add_parser("convert", help="editor format (.vscode/mcp.json) to native Copilot format (.mcp.json)")
    v.add_argument("file", type=Path)
    v.add_argument("--out", type=Path, default=None, help="write here instead of stdout")
    v.add_argument("--add-tools-star", action="store_true", help='add "tools": ["*"] to servers without a tools list')
    args = parser.parse_args(argv)

    try:
        doc = load(args.file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "check":
        report = check(doc)
        print(f"{args.file}: {report.fmt or 'unknown'} format")
        for f in report.findings:
            print(f.line())
        print(f"{report.count('error')} error(s), {report.count('warn')} warning(s), {report.count('info')} note(s)")
        return 1 if report.count("error") or (args.strict and report.count("warn")) else 0

    try:
        result = to_native(doc, add_tools_star=args.add_tools_star)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result.doc, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if result.env_vars:
        print("environment variables to set: " + ", ".join(result.env_vars), file=sys.stderr)
    return 3 if result.skipped else 0
