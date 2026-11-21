"""Shared paths and helpers for the episode 9 tests (run from the episode folder: python3 -m pytest -q tests).

Everything here runs real processes: `dotnet build/test`, the API itself, `git bisect`, dotnet-stack and dotnet-dump.
Work happens in temporary copies of src/orders-app, so the folder in the repository never gets bin/obj, databases or dumps."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
EPISODE = TESTS.parent
APP = EPISODE / "src" / "orders-app"
BUGS = EPISODE / "bugs"
API_PROJECT = Path("src") / "Contoso.Orders.Api" / "Contoso.Orders.Api.csproj"
API_DLL = Path("src") / "Contoso.Orders.Api" / "bin" / "Debug" / "net10.0" / "Contoso.Orders.Api.dll"

sys.path.insert(0, str(APP / "tools"))

needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def dotnet_env(**extra: str) -> dict:
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", MSBUILDDISABLENODEREUSE="1")
    env.pop("ORDERS_SQLSERVER_TESTS", None)
    env.update(extra)
    return env


def copy_app(dest: Path) -> Path:
    """A clean copy of the app (no bin/obj/TestResults) to run real commands in."""
    target = dest / "orders-app"
    shutil.copytree(APP, target, ignore=shutil.ignore_patterns("bin", "obj", "TestResults", "__pycache__", "triage", "*.db*"))
    return target


def apply_patch(app: Path, name: str) -> None:
    """The bug as a patch against the healthy source: what the recording applies with `git apply bugs/<name>`."""
    subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-i", str(BUGS / name)], cwd=app, check=True,
                   capture_output=True, text=True)


def run(cmd: list[str], cwd: Path, timeout: int = 600, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=dotnet_env(**env), capture_output=True, text=True, timeout=timeout)


def build_api(app: Path) -> Path:
    result = run(["dotnet", "build", str(API_PROJECT), "-m:1", "--nologo", "-v", "q"], app)
    assert result.returncode == 0, result.stdout + result.stderr
    return app / API_DLL


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def running_api(app: Path, port: int, extra_env: dict | None = None):
    """The built API as its own process, in Production mode, JSON logs with scopes, a throwaway SQLite file.
    Only the process started here is ever stopped."""
    dll = app / API_DLL
    log = app / "api.log"
    settings = {"ASPNETCORE_URLS": f"http://127.0.0.1:{port}", "ASPNETCORE_ENVIRONMENT": "Production",
                "ConnectionStrings__Orders": f"Data Source={app / 'orders.db'}",
                "Logging__Console__FormatterName": "json", "Logging__Console__FormatterOptions__IncludeScopes": "true",
                **(extra_env or {})}
    env = dotnet_env(**settings)
    with log.open("w") as out:
        proc = subprocess.Popen(["dotnet", str(dll)], cwd=dll.parent, env=env, stdout=out, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"API exited early ({proc.returncode}):\n{log.read_text()}")
            try:
                get(f"http://127.0.0.1:{port}/healthz")
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("API did not answer /healthz in 60 s")
        yield proc, log
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def get(url: str, headers: dict | None = None, method: str = "GET", timeout: float = 10) -> tuple[int, dict, str]:
    """(status, headers, body); 4xx/5xx are returned, not raised. Connection problems and timeouts raise OSError."""
    request = urllib.request.Request(url, headers=headers or {}, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


def jsonc(path: Path) -> dict:
    """VS Code's .json files allow comments. Strip whole-line // comments, then parse."""
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not re.match(r"\s*//", line))
    return json.loads(text)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
