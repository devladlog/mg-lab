#!/usr/bin/env python3
"""review_kit command line. Exit 0 = fine, 1 = the check failed, 2 = usage error. Markdown goes to stdout and,
when $GITHUB_STEP_SUMMARY is set, to the job summary too."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from review_kit import comments, description, metrics, owners, size  # noqa: E402


def emit(text: str) -> None:
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n\n")


def cmd_size(a) -> int:
    report = size.analyze(size.diff_numstat(a.base, a.head))
    emit(size.render(report))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"label=size/{report.label}\nlines={report.lines}\n")
    order = [n for n, _ in size.DEFAULT_LIMITS] + ["XL"]
    if a.fail_above and order.index(report.label) > order.index(a.fail_above):
        print(f"✗ size/{report.label} is above size/{a.fail_above}: split it, or say in the description why it can't be split")
        return 1
    return 0


def cmd_description(a) -> int:
    body = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    problems = description.check(body)
    if problems:
        emit("The pull request description is missing what a reviewer needs:\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    print(f"✓ description has: {', '.join(description.REQUIRED)}")
    return 0


def cmd_owners(a) -> int:
    rules, warnings = owners.parse(Path(a.codeowners).read_text(encoding="utf-8"))
    files = [c.path for c in size.diff_numstat(a.base, a.head)]
    routing = owners.route(files, rules)
    emit(owners.render(routing, warnings))
    return 1 if (a.require_owner and () in routing) else 0


def cmd_comments(a) -> int:
    items = json.loads(Path(a.file).read_text(encoding="utf-8"))
    parsed = comments.load(items)
    emit(comments.render(parsed))
    problems = comments.lint(parsed)
    for p in problems:
        print(f"✗ {p}")
    return 1 if problems else 0


def cmd_metrics(a) -> int:
    rows = metrics.fetch(a.repo, a.limit)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        emit(metrics.render(rows))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="review_kit", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("size", help="size label and lines per area of base...head")
    p.add_argument("--base", required=True); p.add_argument("--head", required=True)
    p.add_argument("--fail-above", choices=["S", "M", "L"], help="exit 1 above this size")
    p.set_defaults(fn=cmd_size)
    p = sub.add_parser("description", help="check a pull request description (file or - for stdin)")
    p.add_argument("file", nargs="?", default="-")
    p.set_defaults(fn=cmd_description)
    p = sub.add_parser("owners", help="who has to review the files changed in base...head")
    p.add_argument("--base", required=True); p.add_argument("--head", required=True)
    p.add_argument("--codeowners", default=".github/CODEOWNERS")
    p.add_argument("--require-owner", action="store_true", help="exit 1 when a changed file has no owner")
    p.set_defaults(fn=cmd_owners)
    p = sub.add_parser("comments", help="lint and summarize review comments (JSON from gh api .../pulls/N/comments)")
    p.add_argument("file")
    p.set_defaults(fn=cmd_comments)
    p = sub.add_parser("metrics", help="time to first review and to merge of the last closed pull requests (needs gh)")
    p.add_argument("--repo", required=True, help="owner/repo"); p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_metrics)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
