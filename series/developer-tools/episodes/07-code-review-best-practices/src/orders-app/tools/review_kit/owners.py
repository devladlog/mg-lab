"""Who has to review this pull request? CODEOWNERS, read the way GitHub reads it.

Rules from GitHub's documentation (About code owners): the last matching pattern wins; patterns follow most of
gitignore, but escaping a leading `#`, negation with `!` and character ranges `[ ]` are not supported, and lines
with invalid syntax are skipped; owners are @user, @org/team or an email address; paths are case sensitive; a path
that matches a pattern with no owner has no code owner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

OWNER = re.compile(r"^(@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9._-]+)?|[^@\s]+@[^@\s]+\.[^@\s]+)$")


@dataclass
class Rule:
    pattern: str
    owners: tuple[str, ...]
    line: int
    regex: re.Pattern[str]


def _translate(pattern: str) -> re.Pattern[str]:
    """gitignore-style pattern to a regex over repo-relative paths ('/' separators)."""
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    dir_only = pattern.endswith("/")
    p = pattern.strip("/")
    i, out = 0, ""
    while i < len(p):
        c = p[i]
        if c == "*":
            if p[i:i + 3] == "**/":
                out += "(?:.*/)?"
                i += 3
                continue
            if p[i:i + 2] == "**":
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    prefix = "" if anchored else "(?:.*/)?"
    # a pattern matches the path itself and, for a directory, everything below it
    tail = "/.*" if dir_only else "(?:/.*)?"
    return re.compile("^" + prefix + out + tail + "$")


def parse(text: str) -> tuple[list[Rule], list[str]]:
    """Returns (rules in file order, warnings for lines GitHub would skip)."""
    rules, warnings = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #", 1)[0].strip() if not raw.lstrip().startswith("#") else ""
        if not line:
            continue
        pattern, *owners = line.split()
        if pattern.startswith("!") or "[" in pattern or pattern.startswith("\\#"):
            warnings.append(f"line {n}: '{pattern}' uses syntax CODEOWNERS doesn't support (!, [ ], \\#): GitHub skips the line")
            continue
        bad = [o for o in owners if not OWNER.match(o)]
        if bad:
            warnings.append(f"line {n}: invalid owner {', '.join(bad)}: GitHub skips the line")
            continue
        rules.append(Rule(pattern, tuple(owners), n, _translate(pattern)))
    return rules, warnings


def owners_for(path: str, rules: list[Rule]) -> tuple[str, ...]:
    for rule in reversed(rules):                      # the last matching pattern takes precedence
        if rule.regex.match(path):
            return rule.owners
    return ()


def route(paths: list[str], rules: list[Rule]) -> dict[tuple[str, ...], list[str]]:
    """Owner set -> files. The empty tuple holds the files nobody owns."""
    out: dict[tuple[str, ...], list[str]] = {}
    for p in paths:
        out.setdefault(owners_for(p, rules), []).append(p)
    return out


def render(routing: dict[tuple[str, ...], list[str]], warnings: list[str]) -> str:
    lines = ["| Owner (any one of them satisfies the review) | Files |", "|---|---|"]
    for owners, files in sorted(routing.items(), key=lambda kv: (not kv[0], kv[0])):
        who = " or ".join(owners) if owners else "**nobody** (any writer can approve)"
        lines.append(f"| {who} | {', '.join(f'`{f}`' for f in files)} |")
    lines += [f"\nWarning: {w}" for w in warnings]
    return "\n".join(lines)
