from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import assign, instructions, issue_lint, review_gate, setup_steps
from .findings import has_errors, render


def _report(findings, ok_text: str) -> int:
    print(render(findings, ok_text))
    return 1 if has_errors(findings) else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent_ready", description="Preflight checks for GitHub Copilot cloud agent and code review")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup-steps", help="validate copilot-setup-steps.yml")
    s.add_argument("file")
    i = sub.add_parser("issue", help="is this issue ready to assign to Copilot?")
    i.add_argument("file")
    n = sub.add_parser("instructions", help="lint copilot-instructions.md, *.instructions.md and AGENTS.md")
    n.add_argument("repo")

    a = sub.add_parser("assign", help="assign an issue to Copilot cloud agent (dry run unless --execute)")
    a.add_argument("repo", help="OWNER/REPO")
    a.add_argument("issue", type=int)
    a.add_argument("--base", default="main")
    a.add_argument("--instructions", default="", help="extra instructions for this task")
    a.add_argument("--model", default="")
    a.add_argument("--execute", action="store_true", help="really call the GitHub API through `gh api`")

    r = sub.add_parser("review", help="request a Copilot code review (dry run unless --execute)")
    r.add_argument("repo")
    r.add_argument("pull", type=int)
    r.add_argument("--execute", action="store_true")

    g = sub.add_parser("gate", help="is a Copilot pull request ready for a human to merge?")
    g.add_argument("--requested-by", required=True, help="login of the person who assigned the task")
    g.add_argument("--repo", help="OWNER/REPO (reads with gh api)")
    g.add_argument("--pull", type=int)
    g.add_argument("--pr-json")
    g.add_argument("--reviews-json")
    g.add_argument("--runs-json")

    args = p.parse_args(argv)
    try:
        if args.cmd == "setup-steps":
            return _report(setup_steps.check_file(args.file), "copilot-setup-steps.yml: OK")
        if args.cmd == "issue":
            return _report(issue_lint.check_file(args.file), "issue: ready to assign")
        if args.cmd == "instructions":
            return _report(instructions.check_repo(args.repo), "instructions: OK")
        if args.cmd in ("assign", "review"):
            req = (assign.assignment_request(args.repo, args.issue, args.base, args.instructions, args.model)
                   if args.cmd == "assign" else assign.review_request(args.repo, args.pull))
            print(req.describe())
            if not args.execute:
                print("\n(dry run: add --execute to send it with `gh api`)")
                return 0
            res = assign.send(req)
            print("\nGitHub answered:", json.dumps({k: res[k] for k in ("number", "html_url", "state", "assignees") if k in res}, default=str)[:600])
            return 0
        if args.cmd == "gate":
            if args.pr_json:
                pr = json.loads(Path(args.pr_json).read_text(encoding="utf-8"))
                reviews = json.loads(Path(args.reviews_json).read_text(encoding="utf-8")) if args.reviews_json else []
                runs = json.loads(Path(args.runs_json).read_text(encoding="utf-8")) if args.runs_json else []
                runs = runs.get("workflow_runs", runs) if isinstance(runs, dict) else runs
            elif args.repo and args.pull:
                pr, reviews, runs = review_gate.fetch(args.repo, args.pull)
            else:
                p.error("gate needs --repo and --pull, or --pr-json")
            verdict = review_gate.evaluate(pr, reviews, runs, args.requested_by)
            print(verdict.render())
            return 0 if verdict.ready else 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2
