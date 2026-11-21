"""Does the pull request description give a reviewer what they need? Sections present and actually filled in."""
from __future__ import annotations

import re
from dataclasses import dataclass

# The template in .github/pull_request_template.md has these four. "Out of scope" is optional.
REQUIRED = ("What and why", "How to verify", "Where to look", "Risk and rollback")
MIN_CHARS = 20
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE = re.compile(r"^\s*(```|~~~)")
_PLACEHOLDER = re.compile(r"^\W*(tbd|todo|n/?a|none|\.\.\.|-)\W*$", re.I)


@dataclass
class Finding:
    section: str
    problem: str

    def __str__(self) -> str:
        return f"{self.section}: {self.problem}"


def sections(body: str) -> dict[str, str]:
    """Level-2 headings (outside code fences) mapped to their text, with HTML comments removed."""
    body = _COMMENT.sub("", body.replace("\r\n", "\n"))
    out: dict[str, list[str]] = {}
    current, fenced = None, False
    for line in body.split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
        m = None if fenced else re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if m:
            current = m.group(1).strip()
            out.setdefault(current, [])
        elif current is not None:
            out[current].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _content(text: str) -> str:
    """The text a human wrote: unchecked/checked task boxes and bare bullets don't count as content."""
    kept = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*[-*]\s*(\[[ xX]\])?\s*", "", line).strip()
        if line and not _PLACEHOLDER.match(line):
            kept.append(line)
    return " ".join(kept)


def check(body: str, required=REQUIRED, min_chars: int = MIN_CHARS) -> list[Finding]:
    found = {name.lower(): text for name, text in sections(body).items()}
    problems = []
    for name in required:
        if name.lower() not in found:
            problems.append(Finding(name, "section is missing"))
        elif len(_content(found[name.lower()])) < min_chars:
            problems.append(Finding(name, f"is empty or a placeholder (needs at least {min_chars} characters of your own words)"))
    return problems
