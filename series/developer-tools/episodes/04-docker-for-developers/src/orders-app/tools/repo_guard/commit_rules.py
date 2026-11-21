"""Conventional Commits 1.0.0 header check, shared by the commit-msg hook and the CI PR-title job.

The spec only mandates `feat` and `fix`; the other types are the common set from
@commitlint/config-conventional. Change ALLOWED_TYPES to fit your team.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ALLOWED_TYPES = (
    "build", "chore", "ci", "docs", "feat", "fix",
    "perf", "refactor", "revert", "style", "test",
)
MAX_HEADER = 72  # fits `git log --oneline` and the GitHub PR list without truncation

HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)"                         # feat
    r"(?:\((?P<scope>[a-z0-9][a-z0-9._/-]*)\))?"  # (api)
    r"(?P<breaking>!)?"                           # !  = breaking change
    r": (?P<subject>\S.*)$"                       # : add retry to the export job
)

# Messages Git writes for you: leave them alone.
PASSTHROUGH = ("Merge ", 'Revert "', "fixup! ", "squash! ", "amend! ")

SCISSORS = "# ------------------------ >8 ------------------------"


@dataclass
class Result:
    ok: bool
    errors: list[str] = field(default_factory=list)
    type: str | None = None
    scope: str | None = None
    breaking: bool = False


def clean(message: str) -> list[str]:
    """Lines Git would keep: drop comment lines and everything below the scissors line (commit -v)."""
    lines = []
    for line in message.replace("\r\n", "\n").split("\n"):
        if line.startswith(SCISSORS):
            break
        if line.startswith("#"):
            continue
        lines.append(line.rstrip())
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def check_message(message: str, allowed_types: tuple[str, ...] = ALLOWED_TYPES) -> Result:
    lines = clean(message)
    if not lines:
        return Result(False, ["empty commit message"])
    header = lines[0]
    if header.startswith(PASSTHROUGH):
        return Result(True)

    errors: list[str] = []
    m = HEADER_RE.match(header)
    if not m:
        errors.append(
            f"header must look like 'type(scope): subject', got: {header!r}"
        )
        return Result(False, errors)

    ctype, subject = m["type"], m["subject"]
    if ctype not in allowed_types:
        errors.append(f"unknown type {ctype!r}; use one of: {', '.join(allowed_types)}")
    if len(header) > MAX_HEADER:
        errors.append(f"header is {len(header)} characters; keep it to {MAX_HEADER}")
    if subject.endswith("."):
        errors.append("subject must not end with a period")
    if len(lines) > 1 and lines[1] != "":
        errors.append("leave one blank line between the header and the body")

    breaking = bool(m["breaking"]) or any(
        line.startswith(("BREAKING CHANGE: ", "BREAKING-CHANGE: ")) for line in lines[2:]
    )
    return Result(not errors, errors, ctype, m["scope"], breaking)
