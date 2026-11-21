import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SAMPLES = SRC / "samples"
EXTRACTIONS = SRC / "extractions"
SOLUTION = SRC / "solution"

needs_pac = pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")


def load(name: str) -> dict:
    return json.loads((EXTRACTIONS / name).read_text(encoding="utf-8"))
