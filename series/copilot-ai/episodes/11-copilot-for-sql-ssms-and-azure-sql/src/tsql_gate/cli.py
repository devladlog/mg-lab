"""python -m tsql_gate check FILE... [--mode readonly|readwrite] [--json]
   python -m tsql_gate constitution lint FILE
   python -m tsql_gate constitution sql FILE --database NAME [--update]

Exit codes of `check`: 0 nothing to report, 1 warnings, 2 at least one BLOCK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constitution import lint_constitution, parse_constitution, render_tsql
from .gate import RULES, Severity, check_text, exit_code


def _cmd_check(args) -> int:
    worst = 0
    report = []
    for name in args.files:
        text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8-sig")
        findings = check_text(text, mode=args.mode)
        worst = max(worst, exit_code(findings))
        report.append({"file": name, "mode": args.mode, "findings": [f.to_dict() for f in findings]})
        if not args.json:
            print(f"== {name}  (mode: {args.mode})")
            if not findings:
                print("   no findings")
            for f in findings:
                print(f"   {f.severity.value:<5} {f.rule}  line {f.line:<3} {f.message}")
                if f.snippet and args.verbose:
                    print(f"         > {f.snippet}")
            blocks = sum(f.severity == Severity.BLOCK for f in findings)
            warns = sum(f.severity == Severity.WARN for f in findings)
            verdict = "BLOCKED" if blocks else ("review" if warns else "ok")
            print(f"   -> {verdict}: {blocks} block, {warns} warning")
    if args.json:
        print(json.dumps(report, indent=2))
    return worst


def _cmd_constitution(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8-sig")
    if args.action == "lint":
        problems = lint_constitution(text)
        c = parse_constitution(text)
        print(f"agentExecuteAsUser: {c.execute_as_user or '(none)'}")
        for p in problems:
            print(f"  problem: {p}")
        print("ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    sys.stdout.write(render_tsql(text, args.database, update=args.update))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tsql_gate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="review T-SQL files before running them")
    c.add_argument("files", nargs="+", help="T-SQL files, or - for stdin")
    c.add_argument("--mode", choices=["readonly", "readwrite"], default="readonly")
    c.add_argument("--json", action="store_true")
    c.add_argument("-v", "--verbose", action="store_true", help="show the offending text")
    c.set_defaults(fn=_cmd_check)
    k = sub.add_parser("constitution", help="lint a CONSTITUTION.md or render its T-SQL")
    k.add_argument("action", choices=["lint", "sql"])
    k.add_argument("file")
    k.add_argument("--database", default="ContosoCopilot")
    k.add_argument("--update", action="store_true", help="emit sp_updateextendedproperty instead of sp_addextendedproperty")
    k.set_defaults(fn=_cmd_constitution)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
