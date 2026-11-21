"""Is a Copilot pull request ready for a human to merge?

Facts (docs.github.com, "Risks and mitigations", "Use code review", read 21 Nov 2026):
  - a human must review and merge the agent's draft pull request; the agent cannot mark it ready, approve or merge
  - the user who asked for the pull request cannot approve it
  - workflows do not run on the agent's changes until someone with write access clicks "Approve and run workflows"
  - a Copilot code review is a "Comment" review by default, so it never counts toward required approvals

Input is what `gh api` returns for the pull request, its reviews, and the workflow runs of the head commit. The author
login of the agent's pull request is matched against the names below; confirm it on your tenant when you record.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

AGENT_AUTHORS = {"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"}
REVIEW_BOT = {"copilot-pull-request-reviewer", "copilot-pull-request-reviewer[bot]"}


@dataclass
class Check:
    name: str
    status: str  # "ok" | "wait" | "block"
    detail: str


@dataclass
class Verdict:
    checks: list[Check]

    @property
    def ready(self) -> bool:
        return all(c.status == "ok" for c in self.checks)

    def render(self) -> str:
        mark = {"ok": "OK   ", "wait": "WAIT ", "block": "BLOCK"}
        lines = [f"{mark[c.status]} {c.name}: {c.detail}" for c in self.checks]
        lines.append("Verdict: " + ("ready for a human to merge" if self.ready else "not ready"))
        return "\n".join(lines)


def _login(user: dict | None) -> str:
    return ((user or {}).get("login") or "").lower()


def evaluate(pr: dict, reviews: list[dict], runs: list[dict], requested_by: str) -> Verdict:
    checks: list[Check] = []
    author = _login(pr.get("user"))
    is_agent = author in AGENT_AUTHORS
    checks.append(Check("author", "ok" if is_agent else "wait", f"opened by {pr.get('user', {}).get('login', '?')}" + ("" if is_agent else " (not the Copilot agent: rules for human pull requests apply)")))

    if pr.get("merged"):
        return Verdict(checks + [Check("state", "ok", "already merged")])
    if pr.get("state") == "closed":
        return Verdict(checks + [Check("state", "block", "closed without merge")])
    checks.append(Check("draft", "wait" if pr.get("draft") else "ok", "still a draft: a human must mark it ready for review" if pr.get("draft") else "ready for review"))

    # Latest review per reviewer decides; submitted_at order as returned by the API (oldest first).
    latest: dict[str, dict] = {}
    for r in sorted((r for r in reviews if r.get("state") != "PENDING"), key=lambda r: r.get("submitted_at") or ""):
        latest[_login(r.get("user"))] = r
    requester = requested_by.lower()
    changes = [u for u, r in latest.items() if r["state"] == "CHANGES_REQUESTED"]
    if changes:
        checks.append(Check("changes requested", "block", "by " + ", ".join(sorted(changes))))
    human_approvals = [u for u, r in latest.items() if r["state"] == "APPROVED" and u not in REVIEW_BOT and u != requester and not u.endswith("[bot]")]
    self_approved = requester in latest and latest[requester]["state"] == "APPROVED"
    if human_approvals:
        checks.append(Check("human approval", "ok", "approved by " + ", ".join(sorted(human_approvals))))
    else:
        detail = "no approval from a person other than the requester"
        if self_approved:
            detail += f" ({requested_by}'s own approval does not count)"
        checks.append(Check("human approval", "wait", detail))
    bot = [r for u, r in latest.items() if u in REVIEW_BOT]
    if bot:
        checks.append(Check("Copilot code review", "ok", f"left a {bot[0]['state']} review (advisory: it does not count as approval)"))
    else:
        checks.append(Check("Copilot code review", "ok", "not requested (optional and advisory: request it in Reviewers)"))

    if not runs:
        checks.append(Check("workflows", "wait", "no workflow runs for the head commit: click Approve and run workflows"))
    else:
        pending = [r for r in runs if r.get("conclusion") == "action_required"]
        running = [r for r in runs if r.get("status") in ("queued", "in_progress", "waiting", "pending")]
        failed = [r for r in runs if r.get("conclusion") in ("failure", "timed_out", "cancelled", "startup_failure")]
        if pending:
            checks.append(Check("workflows", "wait", f"{len(pending)} run(s) waiting for approval: click Approve and run workflows"))
        elif failed:
            checks.append(Check("workflows", "block", "failed: " + ", ".join(sorted({r.get('name', '?') for r in failed}))))
        elif running:
            checks.append(Check("workflows", "wait", f"{len(running)} run(s) still going"))
        else:
            checks.append(Check("workflows", "ok", f"{len(runs)} run(s) passed"))
    return Verdict(checks)


Runner = Callable[..., subprocess.CompletedProcess]


def _gh_json(path: str, runner: Runner) -> dict | list:
    proc = runner(["gh", "api", path], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return json.loads(proc.stdout)


def fetch(repo: str, number: int, runner: Runner = subprocess.run) -> tuple[dict, list[dict], list[dict]]:
    """Read the pull request, its reviews and the workflow runs of its head commit with the GitHub CLI (read-only)."""
    pr = _gh_json(f"/repos/{repo}/pulls/{number}", runner)
    reviews = _gh_json(f"/repos/{repo}/pulls/{number}/reviews?per_page=100", runner)
    sha = pr["head"]["sha"]
    runs = _gh_json(f"/repos/{repo}/actions/runs?head_sha={sha}&per_page=100", runner)
    return pr, list(reviews), list(runs.get("workflow_runs", []))
