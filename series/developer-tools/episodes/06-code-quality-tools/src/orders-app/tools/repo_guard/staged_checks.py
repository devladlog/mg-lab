"""pre-commit checks on what is actually staged (the index), not on the working tree.

- no commits straight onto a protected branch
- no file over the size budget
- no obvious secrets (private keys, GitHub tokens, storage account keys, hard-coded passwords)

A line can opt out with the pragma `guard: allow` (for test fixtures and docs). Use it rarely: reviewers see it.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

PROTECTED_BRANCHES = ("main", "master")
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # GitHub warns at 50 MiB and blocks at 100 MiB; we stop far earlier
ALLOW_PRAGMA = "guard: allow"

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_.\-]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "storage account key": re.compile(r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}"),
    "hard-coded password": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key)\b\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
    ),
}


@dataclass
class Finding:
    path: str
    line: int  # 0 = whole file
    kind: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.kind}"


def git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def scan_text(path: str, text: str) -> list[Finding]:
    findings = []
    for n, line in enumerate(text.splitlines(), start=1):
        if ALLOW_PRAGMA in line:
            continue
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding(path, n, kind))
    return findings


def current_branch(cwd: str | None = None) -> str | None:
    """Branch name, or None when HEAD is detached."""
    r = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=cwd)
    return r.stdout.decode().strip() or None


def has_commits(cwd: str | None = None) -> bool:
    return git("rev-parse", "--verify", "--quiet", "HEAD", cwd=cwd).returncode == 0


def staged_paths(cwd: str | None = None) -> list[str]:
    r = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", cwd=cwd)
    return [p for p in r.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def check_branch(cwd: str | None = None, env: dict | None = None) -> list[str]:
    env = os.environ if env is None else env
    branch = current_branch(cwd)
    if env.get("GUARD_ALLOW_MAIN") == "1" or branch not in PROTECTED_BRANCHES:
        return []
    if not has_commits(cwd):  # the very first commit of a new repo
        return []
    return [f"you are on '{branch}'. Create a branch first: git switch -c feature/<short-name>"]


def check_staged(cwd: str | None = None, max_bytes: int | None = None) -> list[Finding]:
    if max_bytes is None:
        max_bytes = int(os.environ.get("GUARD_MAX_BYTES", DEFAULT_MAX_BYTES))
    findings: list[Finding] = []
    for path in staged_paths(cwd):
        size = int(git("cat-file", "-s", f":{path}", cwd=cwd).stdout or 0)
        if size > max_bytes:
            findings.append(
                Finding(path, 0, f"{size:,} bytes, over the {max_bytes:,} byte budget (use Git LFS or a release asset)")
            )
            continue
        blob = git("show", f":{path}", cwd=cwd).stdout  # the STAGED version
        if b"\0" in blob[:8000]:
            continue  # binary
        findings.extend(scan_text(path, blob.decode("utf-8", "replace")))
    return findings


def scan_tree(cwd: str | None = None) -> list[Finding]:
    """CI backstop: scan every tracked file (catches `git commit --no-verify`)."""
    r = git("ls-files", "-z", cwd=cwd)
    findings: list[Finding] = []
    for path in [p for p in r.stdout.decode("utf-8", "surrogateescape").split("\0") if p]:
        full = os.path.join(cwd or ".", path)
        try:
            with open(full, "rb") as fh:
                blob = fh.read()
        except OSError:
            continue
        if b"\0" in blob[:8000]:
            continue
        findings.extend(scan_text(path, blob.decode("utf-8", "replace")))
    return findings
