"""Shared helpers. Everything that needs .NET runs on throwaway copies of src/orders-app, one build at a time."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[1]
APP = EPISODE / "src" / "orders-app"
TOOL = APP / "tools" / "vs_files.py"
LEARN_IDS = EPISODE / "tests" / "fixtures" / "learn-component-ids.txt"
SMOKE_NAMES = 4  # three [Fact, Trait("Category", "Smoke")] from episode 1's tests plus RunSettingsTests

IGNORE = shutil.ignore_patterns("bin", "obj", ".nuget", "TestResults", "orders.db*", "__pycache__", ".ruff_cache", ".vs")


def run(args, cwd, env, timeout=900, check=False):
    """Runs a command, returns (exit code, combined output)."""
    done = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    out = done.stdout + done.stderr
    if check:
        assert done.returncode == 0, f"{args} exited {done.returncode}\n{out[-3000:]}"
    return done.returncode, out


def tool(*args, cwd=None):
    return run(["python3", "-I", str(TOOL), *map(str, args)], cwd or APP, os.environ.copy(), 60)


@pytest.fixture(scope="session")
def dotnet_env(tmp_path_factory):
    """One packages folder for the whole run (NUGET_PACKAGES wins over nuget.config), deleted with the session."""
    env = os.environ.copy()
    env["NUGET_PACKAGES"] = os.environ.get("EP12_NUGET_CACHE") or str(tmp_path_factory.mktemp("nuget"))
    env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
    return env


def copy_app(dest: Path) -> Path:
    shutil.copytree(APP, dest, ignore=IGNORE)
    return dest


@pytest.fixture(scope="module")
def built(tmp_path_factory, dotnet_env):
    """A copy of the app with the tests filter built once (restore, build api and tests)."""
    repo = copy_app(tmp_path_factory.mktemp("built") / "orders-app")
    run(["dotnet", "build", "OrdersApp.Tests.slnf", "-m:1"], repo, dotnet_env, check=True)
    return repo


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port: int, path: str, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read())


def wait_for(port: int, path: str, timeout: int, predicate=lambda body: True):
    """Polls until the endpoint answers and predicate(body) is true; returns the body or fails with the last error."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            body = get(port, path)
            if predicate(body):
                return body
            last = body
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
            last = error
        time.sleep(0.5)
    pytest.fail(f"{path} on port {port} did not reach the expected state within {timeout}s; last: {last!r}")


@contextlib.contextmanager
def server(args, cwd, env, log: Path):
    """Starts a process in its own process group and always kills that group (never anyone else's processes)."""
    with open(log, "w") as out:
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        yield proc
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, sig)
            try:
                proc.wait(timeout=10)
                break
            except subprocess.TimeoutExpired:
                continue


def app_pids(group: int) -> list[int]:
    """Process ids in the group whose command line is the built API (not dotnet run / dotnet watch)."""
    listing = subprocess.run(["ps", "-eo", "pid,pgid,args"], capture_output=True, text=True).stdout.splitlines()[1:]
    pids = []
    for line in listing:
        pid, pgid, args = line.split(None, 2)
        if int(pgid) == group and "Contoso.Orders.Api --urls" in args and "dotnet" not in args.split()[0].split("/")[-1]:
            pids.append(int(pid))
    return pids
