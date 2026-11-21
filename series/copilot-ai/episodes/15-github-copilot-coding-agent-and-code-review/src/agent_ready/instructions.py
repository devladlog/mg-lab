"""Lint the Copilot instruction files of a repository.

Facts used (docs.github.com, read 21 Nov 2026):
  - repository-wide: .github/copilot-instructions.md; path-specific: .github/instructions/**/*.instructions.md with
    `applyTo` in YAML frontmatter; agent instructions: AGENTS.md at the repository root
  - keep a single file under about 1,000 lines (the earlier 4,000 character limit for code review was removed,
    GitHub changelog 12 June 2026)
  - code review does not support instructions that change formatting or UX of its comments, modify the pull request
    overview comment, change core function (blocking merges, changelog entries), follow external links, or ask for
    vague quality ("be more accurate")
  - the cloud agent needs to know how to build and test: put the commands in the instructions
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .findings import Finding

MAX_LINES = 1000
UNSUPPORTED = [
    (r"\b(bold|italic|emoji|emojis)\b", "formatting or UX of the review comment is not supported"),
    (r"\bformat(ting)? (of )?(the |your )?(review )?comments?\b", "formatting or UX of the review comment is not supported"),
    (r"\b(pull request|pr) (overview|summary)\b", "changing the pull request overview comment is not supported"),
    (r"\b(block|prevent|stop)\w* (the )?(merge|merging)\b", "blocking merges is not something instructions can do: use rulesets"),
    (r"\bchangelog\b", "generating changelog entries is not supported"),
    (r"https?://", "external links are not followed: copy the relevant text into the file"),
    (r"\b(be|being) (more )?(accurate|thorough|careful|precise)\b", "vague quality requests do not change the result: state a concrete rule"),
]
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def discover(repo: Path) -> list[Path]:
    files: list[Path] = []
    for rel in (".github/copilot-instructions.md", "AGENTS.md"):
        if (repo / rel).is_file():
            files.append(repo / rel)
    files += sorted((repo / ".github" / "instructions").glob("**/*.instructions.md"))
    return files


def _repo_files(repo: Path) -> list[str]:
    skip = {".git", "bin", "obj", "node_modules"}
    return [p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file() and not (set(p.relative_to(repo).parts) & skip)]


def _glob_matches(pattern: str, files: list[str]) -> bool:
    # applyTo supports glob patterns; ** spans folders. Translate to a regex.
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            out += ".*"; i += 2
        elif pattern[i] == "*":
            out += "[^/]*"; i += 1
        elif pattern[i] == "?":
            out += "[^/]"; i += 1
        elif pattern[i] == "{":
            j = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(a) for a in pattern[i + 1:j].split(",")) + ")"; i = j + 1
        else:
            out += re.escape(pattern[i]); i += 1
    rx = re.compile(out + r"\Z")
    return any(rx.match(f) for f in files)


def check_file(path: Path, repo: Path, files: list[str] | None = None) -> list[Finding]:
    rel = path.relative_to(repo).as_posix()
    text = path.read_text(encoding="utf-8")
    out: list[Finding] = []
    n_lines = len(text.splitlines())
    if n_lines > MAX_LINES:
        out.append(Finding("warning", "size", f"{rel}: {n_lines} lines; keep a single instruction file under about {MAX_LINES}"))
    if not text.strip():
        return [Finding("error", "empty", f"{rel}: empty")]

    body = text
    if rel.endswith(".instructions.md"):
        m = _FRONT.match(text)
        if not m:
            out.append(Finding("error", "frontmatter", f"{rel}: path-specific instructions need YAML frontmatter with `applyTo`"))
        else:
            body = text[m.end():]
            try:
                meta = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError as exc:
                meta = {}
                out.append(Finding("error", "frontmatter", f"{rel}: frontmatter is not valid YAML ({exc})"))
            apply_to = meta.get("applyTo") if isinstance(meta, dict) else None
            if not apply_to or not isinstance(apply_to, str):
                out.append(Finding("error", "applyTo", f"{rel}: `applyTo` is missing or not a string"))
            elif not _glob_matches(apply_to, files if files is not None else _repo_files(repo)):
                out.append(Finding("warning", "applyTo-nomatch", f"{rel}: applyTo `{apply_to}` matches no file in the repository"))

    for pattern, why in UNSUPPORTED:
        for m in re.finditer(pattern, body, re.I):
            line_no = text[: text.find(m.group(0))].count("\n") + 1 if m.group(0) in text else 0
            out.append(Finding("warning", "unsupported-for-review", f"{rel}:{line_no}: `{m.group(0)}` - {why}"))
            break

    if rel == ".github/copilot-instructions.md":
        if not re.search(r"`[^`]*\b(test|build)\b[^`]*`", body, re.I):
            out.append(Finding("warning", "no-test-command", f"{rel}: no build/test command in backticks: the agent should know how to run the tests"))
    return out


def check_repo(repo: str | Path) -> list[Finding]:
    repo = Path(repo)
    files = discover(repo)
    if not (repo / ".github" / "copilot-instructions.md").is_file():
        out = [Finding("warning", "no-repo-instructions", ".github/copilot-instructions.md is missing: repository-wide instructions are the first thing to add")]
    else:
        out = []
    all_files = _repo_files(repo)
    for f in files:
        out += check_file(f, repo, all_files)
    return out
