import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EP = Path(__file__).resolve().parents[1]
SRC = EP / "src"
sys.path.insert(0, str(SRC / "tools"))


@pytest.fixture(scope="session")
def lint_dll():
    """Builds composite-lint once (dotnet build -m:1) and removes bin and obj when the session ends."""
    if shutil.which("dotnet") is None:
        pytest.skip("dotnet SDK not installed")
    proj = SRC / "CompositeLint"
    r = subprocess.run(["dotnet", "build", str(proj), "-m:1", "-nologo", "-v", "q"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    yield proj / "bin" / "Debug" / "net8.0" / "composite-lint.dll"
    for d in ("bin", "obj"):
        shutil.rmtree(proj / d, ignore_errors=True)


@pytest.fixture()
def run_lint(lint_dll):
    def run(folder: Path, explain=False):
        cmd = ["dotnet", str(lint_dll), str(folder)] + (["--explain"] if explain else [])
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    return run
