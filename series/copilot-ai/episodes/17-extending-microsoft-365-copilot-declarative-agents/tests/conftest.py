import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PACKAGE = SRC / "agent" / "appPackage"


@pytest.fixture
def pkg(tmp_path):
    """A writable copy of the real app package folder."""
    dest = tmp_path / "appPackage"
    shutil.copytree(PACKAGE, dest)
    return dest
