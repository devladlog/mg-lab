"""Shared helpers for the episode 7 tests (run from the episode folder: python3 -m pytest -q tests)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
EPISODE = TESTS.parent
APP = EPISODE / "src" / "orders-app"
DEMO = EPISODE / "src" / "review-demo"
WORKFLOW = APP / ".github" / "workflows" / "pr-review-kit.yml"
FIXTURES = TESTS / "fixtures"
CLI = APP / "tools" / "review_kit" / "cli.py"

sys.path.insert(0, str(APP / "tools"))

needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

GIT_ENV = {"GIT_AUTHOR_NAME": "Alex Demo", "GIT_AUTHOR_EMAIL": "alex.demo@contoso.example",
           "GIT_COMMITTER_NAME": "Alex Demo", "GIT_COMMITTER_EMAIL": "alex.demo@contoso.example",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def new_repo(path: Path, files: dict[str, str | bytes] | None = None) -> Path:
    """A throwaway repository with a first commit on `main`."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    write(path, files or {"README.md": "# demo\n"})
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "chore: first commit")
    return path


def write(root: Path, files: dict[str, str | bytes]) -> None:
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")


def commit(repo: Path, message: str, files: dict[str, str | bytes] | None = None) -> str:
    if files:
        write(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_workflow(path: Path = WORKFLOW) -> dict:
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in wf:                       # YAML 1.1: PyYAML reads the key `on` as boolean True
        wf["on"] = wf.pop(True)
    return wf


def run_cli(*args: str, cwd: Path | None = None, stdin: str | None = None, env: dict | None = None):
    return subprocess.run([sys.executable, str(CLI), *args], cwd=cwd, input=stdin, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})
