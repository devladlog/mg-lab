import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SOLUTION = SRC / "solution"
RELEASE_1_0 = SRC / "releases" / "1.0.0.0"
DEPLOY = SRC / "deploy"

needs_pac = pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")


@pytest.fixture
def sol_copy(tmp_path):
    """A throw-away copy of the current solution to break on purpose."""
    dest = tmp_path / "solution"
    shutil.copytree(SOLUTION, dest)
    return dest


def codes(findings, level=None):
    return sorted({f.code for f in findings if level is None or f.level == level})
