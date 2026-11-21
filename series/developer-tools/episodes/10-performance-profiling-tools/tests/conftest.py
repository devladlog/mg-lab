"""Shared paths and helpers for the episode 10 tests (run from the episode folder: python3 -m pytest -q tests).

The end-to-end test runs real processes: dotnet build, the API in Release mode, tools/load.py, dotnet-counters and dotnet-trace.
Work happens in temporary copies of src/orders-app, so the folder in the repository never gets bin/obj, databases or traces."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
EPISODE = TESTS.parent
APP = EPISODE / "src" / "orders-app"
BUGS = EPISODE / "bugs"
API_DLL = Path("src") / "Contoso.Orders.Api" / "bin" / "Release" / "net10.0" / "Contoso.Orders.Api.dll"

sys.path.insert(0, str(APP / "tools"))

needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")
needs_patch = pytest.mark.skipif(shutil.which("patch") is None, reason="patch not installed")


def dotnet_env(**extra: str) -> dict:
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", MSBUILDDISABLENODEREUSE="1")
    env.update(extra)
    return env


def copy_app(dest: Path, name: str = "orders-app") -> Path:
    target = dest / name
    shutil.copytree(APP, target, ignore=shutil.ignore_patterns("bin", "obj", "TestResults", "__pycache__", "profile", "*.db*"))
    return target


def apply_patch(app: Path, name: str) -> None:
    subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-i", str(BUGS / name)], cwd=app, check=True,
                   capture_output=True, text=True)


def run(cmd: list[str], cwd: Path, timeout: int = 900, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=dotnet_env(**env), capture_output=True, text=True, timeout=timeout)


def build_release(app: Path) -> Path:
    result = run(["dotnet", "build", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-c", "Release", "-m:1", "--nologo", "-v", "q"], app)
    assert result.returncode == 0, result.stdout + result.stderr
    return app / API_DLL


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_healthy(port: int, proc: subprocess.Popen, log: Path, seconds: int = 180) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"API exited early ({proc.returncode}):\n{log.read_text()}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2).close()
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"API did not answer /healthz in {seconds} s")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
