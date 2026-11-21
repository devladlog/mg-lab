"""How long do pull requests wait for a human? Time to first review and to merge, from the GitHub REST API.

Use it to find a queue, never to rank people: a median that drifts up means reviews are waiting, not that someone
is slow. Needs the `gh` CLI (signed in) for `fetch`; `compute` works on plain dictionaries.
"""
from __future__ import annotations

import json
import statistics
import subprocess
from datetime import datetime


def _t(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def compute(pr: dict, reviews: list[dict]) -> dict:
    """One pull request (GET pulls/{n}) and its reviews (GET pulls/{n}/reviews) -> the numbers we track."""
    author = (pr.get("user") or {}).get("login")
    opened = _t(pr["created_at"])
    # PENDING reviews are drafts nobody else can see (no submitted_at); the author's own review doesn't count.
    submitted = sorted((r for r in reviews if r.get("submitted_at") and r.get("state") != "PENDING"
                        and (r.get("user") or {}).get("login") != author), key=lambda r: r["submitted_at"])
    first = _t(submitted[0]["submitted_at"]) if submitted else None
    merged = _t(pr.get("merged_at"))
    hours = lambda a, b: round((b - a).total_seconds() / 3600, 2) if a and b else None
    adds, dels = pr.get("additions"), pr.get("deletions")
    return {
        "number": pr["number"],
        "author": author,
        "lines": adds + dels if isinstance(adds, int) and isinstance(dels, int) else None,
        "hours_to_first_review": hours(opened, first),
        "hours_to_merge": hours(opened, merged),
        "changes_requested": sum(1 for r in submitted if r["state"] == "CHANGES_REQUESTED"),
        "approvals": sum(1 for r in submitted if r["state"] == "APPROVED"),
        "reviewers": sorted({r["user"]["login"] for r in submitted}),
        "merged": merged is not None,
    }


def median(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if r[key] is not None]
    return round(statistics.median(values), 2) if values else None


def render(rows: list[dict]) -> str:
    cell = lambda v: "-" if v is None else str(v)
    lines = ["| PR | Lines | Hours to first review | Hours to merge | Changes requested | Reviewers |", "|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        lines.append(f"| #{r['number']} | {cell(r['lines'])} | {cell(r['hours_to_first_review'])} | {cell(r['hours_to_merge'])} | "
                     f"{r['changes_requested']} | {', '.join(r['reviewers']) or '-'} |")
    lines += ["", f"Median hours to first review: {cell(median(rows, 'hours_to_first_review'))}; "
                  f"median hours to merge: {cell(median(rows, 'hours_to_merge'))} (over {len(rows)} pull requests)"]
    waiting = [r['number'] for r in rows if r['hours_to_first_review'] is None]
    if waiting:
        lines.append("Never reviewed by anyone but the author: " + ", ".join(f"#{n}" for n in waiting))
    return "\n".join(lines)


def gh_json(args: list[str]):
    proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def fetch(repo: str, limit: int = 20) -> list[dict]:
    """The last `limit` closed pull requests of owner/repo, with their reviews."""
    pulls = gh_json([f"repos/{repo}/pulls?state=closed&per_page={limit}&sort=updated&direction=desc"])
    rows = []
    for p in pulls[:limit]:
        pr = gh_json([f"repos/{repo}/pulls/{p['number']}"])        # the list response has no additions/deletions
        reviews = gh_json([f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100"])
        rows.append(compute(pr, reviews))
    return rows
