"""Shared paths and helpers for the episode 8 tests (run from the episode folder: python3 -m pytest -q tests).

The real-run tests need `dotnet` and Newman (`npm ci` in src/orders-app/api-tests); they are skipped, loudly,
when either is missing. node_modules is not kept in the repository."""
from __future__ import annotations

import json
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
API_TESTS = APP / "api-tests"
COLLECTION = API_TESTS / "orders-api.postman_collection.json"
ENVIRONMENT = API_TESTS / "environments" / "local.postman_environment.json"
OPENAPI = API_TESTS / "openapi.v1.json"
WORKFLOW = APP / ".github" / "workflows" / "api-tests.yml"
SCRIPT = APP / "scripts" / "run-api-tests.sh"
NEWMAN = API_TESTS / "node_modules" / ".bin" / "newman"
FIXTURES = TESTS / "fixtures"

sys.path.insert(0, str(API_TESTS / "tools"))

needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")
needs_newman = pytest.mark.skipif(not NEWMAN.exists(), reason="Newman not installed: npm ci in src/orders-app/api-tests")
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_workflow(path: Path = WORKFLOW) -> dict:
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in wf:                       # YAML 1.1: PyYAML reads the key `on` as boolean True
        wf["on"] = wf.pop(True)
    return wf


def action_manifest(action: str) -> dict:
    return yaml.safe_load((FIXTURES / "actions" / (action.replace("/", "_") + ".yml")).read_text())


def pins() -> dict:
    return {k: v for k, v in load_json(FIXTURES / "actions" / "pins.json").items() if not k.startswith("_")}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def dotnet_env(**extra) -> dict:
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", MSBUILDDISABLENODEREUSE="1")
    env.pop("ORDERS_SQLSERVER_TESTS", None)
    env.update(extra)
    return env


def copy_app(dest: Path) -> Path:
    """A clean copy of the app (no bin/obj/node_modules/results) to change and run."""
    target = dest / "orders-app"
    shutil.copytree(APP, target, ignore=shutil.ignore_patterns("bin", "obj", "TestResults", "__pycache__", "node_modules", "results"))
    return target


def run_script(app: Path, results: Path, *args: str, **env_extra) -> subprocess.CompletedProcess:
    env = dotnet_env(RESULTS_DIR=str(results), NEWMAN=str(NEWMAN), **env_extra)
    return subprocess.run(["bash", str(app / "scripts" / "run-api-tests.sh"), *args], cwd=app, env=env,
                          capture_output=True, text=True, timeout=600)


class RunningApi:
    def __init__(self, base_url: str, proc: subprocess.Popen):
        self.base_url, self.proc = base_url, proc


@pytest.fixture(scope="session")
def api(tmp_path_factory):
    """The real API (dotnet run, Production, a throwaway SQLite file) for the whole test session."""
    if shutil.which("dotnet") is None:
        pytest.skip("dotnet SDK not installed")
    tmp = tmp_path_factory.mktemp("api")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = open(tmp / "api.log", "w")
    env = dotnet_env(ASPNETCORE_ENVIRONMENT="Production", Database__Provider="Sqlite",
                     ConnectionStrings__Orders=f"Data Source={tmp / 'orders.db'};Pooling=False", App__Version="test-sha")
    proc = subprocess.Popen(["dotnet", "run", "--project", str(APP / "src" / "Contoso.Orders.Api"), "--no-launch-profile",
                             "--urls", base], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=2).read()
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail("the API exited early:\n" + (tmp / "api.log").read_text())
                time.sleep(1)
        else:
            pytest.fail("the API did not start in 90 s")
        yield RunningApi(base, proc)
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
