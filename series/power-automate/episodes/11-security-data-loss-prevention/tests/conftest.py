import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FLOWS = SRC / "flows"
POLICY = SRC / "policy"

needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
