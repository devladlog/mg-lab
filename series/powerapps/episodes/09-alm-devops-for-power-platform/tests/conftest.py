"""Shared helpers: paths, running pwsh scripts and pac, and throw-away copies of the solution source."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parent.parent
SRC = EPISODE / "src"
SCRIPTS = SRC / "scripts"
SOLUTION = SRC / "solution" / "EquipmentDesk"
SETTINGS = SRC / "settings"
PIPELINES = SRC / "pipelines"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Result:
    def __init__(self, completed):
        self.code = completed.returncode
        self.out = completed.stdout + completed.stderr

    def __repr__(self):
        return f"exit {self.code}\n{self.out}"


def pwsh(script, *args, env=None):
    """Run one of the episode's PowerShell scripts: pwsh -NoProfile -File <script> <args>."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(SCRIPTS / script), *map(str, args)]
    return Result(subprocess.run(cmd, capture_output=True, text=True, env=full_env, timeout=180))


def pac(*args):
    return Result(subprocess.run(["pac", *map(str, args)], capture_output=True, text=True, timeout=180))


@pytest.fixture
def source_copy(tmp_path):
    """A writable copy of src/solution/EquipmentDesk."""
    target = tmp_path / "EquipmentDesk"
    shutil.copytree(SOLUTION, target)
    return target


@pytest.fixture(scope="session")
def pac_version():
    r = pac("help")
    return r.out
