"""Is this issue ready to be assigned to Copilot cloud agent?

GitHub documents what the agent receives: the issue title, description and existing comments, plus the repository's
custom instructions. It does not react to comments added after assignment, and hidden characters (text in an HTML
comment) are filtered out before the agent sees them. This linter turns that into a checklist; the section names are
a team convention (the template in issues/), not a GitHub requirement.
"""
from __future__ import annotations

import re
from pathlib import Path

from .findings import Finding

VAGUE = ["better", "improve", "clean up", "cleanup", "stuff", "etc", "nice", "optimize", "refactor everything", "fix it"]
SECTION_ALIASES = {
    "problem": ("problem", "description", "context", "bug"),
    "criteria": ("acceptance criteria", "done when", "definition of done"),
    "where": ("where to look", "files", "relevant files", "code pointers"),
    "scope": ("out of scope", "non-goals", "not in scope"),
}
_HEADING = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.M)
_CHECKBOX = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+\S", re.M)
_PATHLIKE = re.compile(r"`?[\w.\-]+(?:/[\w.\-]+)+`?|`[\w.\-]+\.(?:cs|ts|py|js|java|kt|json|yml|yaml|csproj)`")
_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)


def _sections(body: str) -> dict[str, str]:
    parts = _HEADING.split(body)
    # parts = [preamble, title1, text1, title2, text2, ...]
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _find(sections: dict[str, str], key: str) -> str | None:
    for alias in SECTION_ALIASES[key]:
        for name, text in sections.items():
            if name == alias:
                return text
    return None


def check_text(text: str) -> list[Finding]:
    out: list[Finding] = []
    lines = text.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
    body = "\n".join(lines[1:]) if title else text

    if not title:
        out.append(Finding("error", "title", "the file must start with `# <issue title>`"))
    elif len(title) < 12:
        out.append(Finding("warning", "title", f"title `{title}` is very short: say what is wrong or what to add"))
    elif len(title) > 100:
        out.append(Finding("warning", "title", "title is over 100 characters"))

    hidden = _HTML_COMMENT.findall(text)
    if hidden:
        out.append(Finding("warning", "hidden-text", f"{len(hidden)} HTML comment(s): GitHub filters hidden text before the agent sees it, so it will be ignored (it is also invisible when the issue is rendered)"))
    visible = _HTML_COMMENT.sub("", body)

    sections = _sections(visible)
    problem = _find(sections, "problem")
    if problem is None or len(problem.strip()) < 40:
        out.append(Finding("error", "problem", "needs a `## Problem` section of at least 40 characters: what happens, with a concrete example"))
    criteria = _find(sections, "criteria")
    if criteria is None:
        out.append(Finding("error", "criteria", "needs `## Acceptance criteria`: the agent finishes when these are true, and so can you check it"))
    elif len(_CHECKBOX.findall(criteria)) < 1:
        out.append(Finding("error", "criteria", "acceptance criteria must be a checklist (`- [ ] ...`)"))
    else:
        if not re.search(r"\d", criteria):
            out.append(Finding("warning", "criteria-values", "no concrete value in the criteria: give example inputs and expected outputs"))
        if not re.search(r"\btests?\b", criteria, re.I):
            out.append(Finding("warning", "criteria-tests", "no criterion mentions tests: say which tests to add or run"))
    where = _find(sections, "where")
    if where is None or not _PATHLIKE.search(where):
        out.append(Finding("warning", "where", "no file paths: add `## Where to look` with the files involved"))
    if _find(sections, "scope") is None:
        out.append(Finding("info", "scope", "no `## Out of scope`: say what the agent must not touch"))

    lowered = visible.lower()
    hits = [w for w in VAGUE if re.search(rf"\b{re.escape(w)}\b", lowered)]
    if hits:
        out.append(Finding("warning", "vague-words", f"vague wording: {', '.join(hits)}. Replace with a measurable outcome"))
    return out


def check_file(path: str | Path) -> list[Finding]:
    return check_text(Path(path).read_text(encoding="utf-8"))
