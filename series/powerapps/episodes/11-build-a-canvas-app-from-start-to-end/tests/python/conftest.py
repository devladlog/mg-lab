"""Shared paths and helpers. Everything here is offline: pac only packs and unpacks, nothing signs in."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[2]
SRC = EPISODE / "src"
SCHEMA_PATH = SRC / "schema" / "contosoinspections.schema.json"
SOLUTION = SRC / "solution" / "ContosoInspections"
APP = SRC / "app" / "Src"
SCRIPTS = SRC / "scripts"


@pytest.fixture(scope="session")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class Result:
    def __init__(self, completed):
        self.code = completed.returncode
        self.out = completed.stdout + completed.stderr

    def __repr__(self):
        return f"exit {self.code}\n{self.out}"


def run(*cmd, timeout=180):
    return Result(subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout))


def pac(*args):
    return run("pac", *args)


@pytest.fixture
def source_copy(tmp_path):
    target = tmp_path / "ContosoInspections"
    shutil.copytree(SOLUTION, target)
    return target
