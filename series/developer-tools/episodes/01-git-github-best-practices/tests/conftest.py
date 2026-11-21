"""Shared fixtures: a throwaway Git repo with the kit copied in, isolated from the user's Git config."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parent.parent
KIT = EPISODE / "src" / "kit"
sys.path.insert(0, str(KIT / "tools"))


class Repo:
    def __init__(self, path: Path, env: dict):
        self.path, self.env = path, env

    def run(self, *args: str, check: bool = True, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        env = {**self.env, **(extra_env or {})}
        r = subprocess.run(args, cwd=self.path, env=env, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def git(self, *args: str, **kw) -> subprocess.CompletedProcess:
        return self.run("git", *args, **kw)

    def write(self, rel: str, content: str | bytes) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes if isinstance(content, bytes) else p.write_text)(content)
        return p

    def commit(self, message: str, *files: str, **kw) -> subprocess.CompletedProcess:
        if files:
            self.git("add", *files)
        return self.git("commit", "-m", message, check=False, **kw)


@pytest.fixture
def clean_env(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Alex Demo", "GIT_AUTHOR_EMAIL": "alex.demo@contoso.com",
        "GIT_COMMITTER_NAME": "Alex Demo", "GIT_COMMITTER_EMAIL": "alex.demo@contoso.com",
        "LANG": "C.UTF-8",
    }
    return env


@pytest.fixture
def repo(tmp_path: Path, clean_env: dict) -> Repo:
    """New repo on `main` with the kit copied in and scripts/setup-dev.sh already run."""
    path = tmp_path / "app"
    shutil.copytree(KIT, path, ignore=shutil.ignore_patterns("__pycache__"))
    r = Repo(path, clean_env)
    r.git("init", "-q", "-b", "main")
    r.run("bash", "scripts/setup-dev.sh")
    return r


@pytest.fixture
def repo_with_history(repo: Repo) -> Repo:
    """Same repo with a first commit on main and a feature branch checked out."""
    res = repo.commit("chore: add repo guardrails", ".")
    assert res.returncode == 0, res.stderr
    repo.git("switch", "-q", "-c", "feature/orders-paging")
    return repo
