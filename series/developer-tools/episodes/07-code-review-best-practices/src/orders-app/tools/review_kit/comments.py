"""Review comments in the Conventional Comments format: `<label> [decorations]: <subject>`.

The label list and the decorations (blocking, non-blocking, if-minor) are from conventionalcomments.org.
House rule on top of the spec (the spec leaves decorations optional): an `issue`, `question`, `todo` or `chore`
must say `(blocking)` or `(non-blocking)`, because without it the author has to guess whether to wait for an
answer. `praise`, `note`, `thought` and `nitpick` are non-blocking by nature.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

LABELS = ("praise", "nitpick", "suggestion", "issue", "todo", "question", "thought", "chore", "note",
          "typo", "polish", "quibble")
MUST_DECLARE = ("issue", "question", "todo", "chore")
_HEAD = re.compile(r"^\s*(?P<label>[a-z]+)(?:\s*\((?P<deco>[^)]*)\))?\s*:\s*(?P<subject>\S.*)$", re.I)


@dataclass
class Comment:
    id: int
    author: str
    path: str | None
    line: int | None
    label: str | None
    decorations: tuple[str, ...]
    subject: str
    is_reply: bool

    @property
    def blocking(self) -> bool:
        return "blocking" in self.decorations

    @property
    def declared(self) -> bool:
        return bool({"blocking", "non-blocking"} & set(self.decorations))


def parse_body(body: str) -> tuple[str | None, tuple[str, ...], str]:
    first = body.strip().split("\n", 1)[0]
    m = _HEAD.match(first)
    if not m or m.group("label").lower() not in LABELS:
        return None, (), first
    deco = tuple(d.strip().lower() for d in (m.group("deco") or "").split(",") if d.strip())
    return m.group("label").lower(), deco, m.group("subject").strip()


def load(items: list[dict]) -> list[Comment]:
    """From `gh api repos/{owner}/{repo}/pulls/{n}/comments --paginate` (REST: id, user.login, path, line, body, in_reply_to_id)."""
    out = []
    for it in items:
        label, deco, subject = parse_body(it.get("body", ""))
        out.append(Comment(it["id"], (it.get("user") or {}).get("login", "?"), it.get("path"), it.get("line"),
                           label, deco, subject, it.get("in_reply_to_id") is not None))
    return out


def lint(comments: list[Comment]) -> list[str]:
    """Problems with the top-level comments (replies are conversation, not review feedback)."""
    problems = []
    for c in comments:
        if c.is_reply:
            continue
        where = f"{c.path}:{c.line}" if c.path else f"comment {c.id}"
        if c.label is None:
            problems.append(f"{where}: no label. Start with one of: {', '.join(LABELS[:9])}")
        elif c.label in MUST_DECLARE and not c.declared:
            problems.append(f"{where}: '{c.label}' must say (blocking) or (non-blocking)")
        elif c.label in ("praise", "note", "thought", "nitpick") and c.blocking:
            problems.append(f"{where}: '{c.label}' can't be blocking: use issue, todo or chore")
    return problems


def summarize(comments: list[Comment]) -> dict:
    top = [c for c in comments if not c.is_reply]
    labels = Counter(c.label or "unlabelled" for c in top)
    return {"comments": len(top), "replies": len(comments) - len(top), "labels": dict(labels),
            "blocking": [c for c in top if c.blocking]}


def render(comments: list[Comment]) -> str:
    s = summarize(comments)
    lines = [f"{s['comments']} review comments, {s['replies']} replies",
             "| Label | Count |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(s["labels"].items(), key=lambda kv: (-kv[1], kv[0]))]
    lines += ["", f"Blocking ({len(s['blocking'])}) — the author has to answer these before merge:"]
    lines += [f"- `{c.path}:{c.line}` {c.label}: {c.subject}" for c in s["blocking"]] or ["- none"]
    return "\n".join(lines)
