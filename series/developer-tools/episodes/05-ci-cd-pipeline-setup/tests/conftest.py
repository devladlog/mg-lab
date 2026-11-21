"""Shared paths and helpers for the episode 5 tests (run from the episode folder: python3 -m pytest -q tests)."""
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
WORKFLOW = APP / ".github" / "workflows" / "ci-cd.yml"
FIXTURES = TESTS / "fixtures"

sys.path.insert(0, str(APP / "tools"))


def load_workflow(path: Path = WORKFLOW) -> dict:
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in wf:                       # YAML 1.1: PyYAML reads the key `on` as boolean True
        wf["on"] = wf.pop(True)
    return wf


def action_manifest(action: str) -> dict:
    return yaml.safe_load((FIXTURES / "actions" / (action.replace("/", "_") + ".yml")).read_text())


def pins() -> dict:
    return {k: v for k, v in json.loads((FIXTURES / "actions" / "pins.json").read_text()).items()
            if not k.startswith("_")}


def copy_app(dest: Path) -> Path:
    """A clean copy of the app (no bin/obj/TestResults) to run real commands in."""
    target = dest / "orders-app"
    shutil.copytree(APP, target, ignore=shutil.ignore_patterns("bin", "obj", "TestResults", "__pycache__", ".env"))
    return target


def dotnet_env() -> dict:
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", MSBUILDDISABLENODEREUSE="1")
    env.pop("ORDERS_SQLSERVER_TESTS", None)
    return env


def run(cmd, cwd: Path, env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                          shell=isinstance(cmd, str))


needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")
needs_bicep = pytest.mark.skipif(shutil.which("bicep") is None, reason="bicep CLI not installed")
