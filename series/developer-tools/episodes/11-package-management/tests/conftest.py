"""Shared helpers: run the real dotnet, work on throwaway copies of the repository, share one NuGet cache."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[1]
APP = EPISODE / "src" / "orders-app"
CONSUMER = EPISODE / "src" / "consumer"
FIXTURES = Path(__file__).parent / "fixtures"
SKIP_DIRS = {"bin", "obj", ".nuget", ".venv", "artifacts", "TestResults", ".ruff_cache", ".pytest_cache", "__pycache__"}

needs_dotnet = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")


def copy_tree(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst, ignore=lambda _d, names: [n for n in names if n in SKIP_DIRS])
    return dst


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """Runs a command and returns it with stdout and stderr joined (never raises unless check=True)."""
    full_env = {**os.environ, **(env or {})}
    proc = subprocess.run(cmd, cwd=cwd, env=full_env, capture_output=True, text=True, check=False)
    proc.output = proc.stdout + proc.stderr  # type: ignore[attr-defined]
    if check and proc.returncode != 0:
        raise AssertionError(f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.output}")  # type: ignore[attr-defined]
    return proc


@pytest.fixture(scope="session")
def nuget_cache(tmp_path_factory) -> Path:
    """One global packages folder for every test that doesn't test the packages folder itself."""
    path = tmp_path_factory.mktemp("global-packages")
    return path


@pytest.fixture(scope="session")
def dotnet_env(nuget_cache) -> dict[str, str]:
    return {
        "NUGET_PACKAGES": str(nuget_cache),          # overrides globalPackagesFolder from nuget.config
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "MSBUILDDISABLENODEREUSE": "1",
        "DOTNET_CLI_UI_LANGUAGE": "en",
    }


@pytest.fixture
def app(tmp_path) -> Path:
    """A fresh copy of src/orders-app (no bin/obj) to change and break."""
    return copy_tree(APP, tmp_path / "orders-app")


@pytest.fixture
def consumer(tmp_path) -> Path:
    return copy_tree(CONSUMER, tmp_path / "consumer")


@pytest.fixture(scope="session")
def restored_app(tmp_path_factory, dotnet_env) -> Path:
    """The repository copied once and restored, so tests that only read it don't pay for a restore each."""
    root = copy_tree(APP, tmp_path_factory.mktemp("restored") / "orders-app")
    run(["dotnet", "restore", "-m:1"], root, dotnet_env, check=True)
    return root
