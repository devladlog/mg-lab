import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
for sub in ("data", "reference", "tools"):
    sys.path.insert(0, str(SRC / sub))
