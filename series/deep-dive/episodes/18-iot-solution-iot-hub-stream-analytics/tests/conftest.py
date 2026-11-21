from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASA = ROOT / "asa"
CASES = Path(__file__).parent / "asa_cases"
CLI = ROOT / "node_modules" / ".bin" / "azure-streamanalytics-cicd"


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def template() -> dict:
    """infra/main.bicep compiled by the real Bicep CLI."""
    if not shutil.which("bicep"):
        pytest.skip("bicep CLI not on PATH")
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


@pytest.fixture(scope="session")
def resources(template) -> list[dict]:
    res = template["resources"]
    return res if isinstance(res, list) else list(res.values())


def of_type(resources: list[dict], type_name: str) -> list[dict]:
    return [r for r in resources if r["type"] == type_name]


@pytest.fixture(scope="session")
def asa_cli() -> Path:
    if not CLI.exists():
        pytest.skip("azure-streamanalytics-cicd not installed: run `npm ci --no-audit --no-fund` in the episode folder")
    if not shutil.which("dotnet"):
        pytest.skip("dotnet SDK 8 or later is required by the Stream Analytics local runtime")
    return CLI
