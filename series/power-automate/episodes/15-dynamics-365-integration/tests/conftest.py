import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SOLUTION = SRC / "solution"
SAMPLES = SRC / "samples"
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
WON = "Wonopportunityfollowup"
DIGEST = "Overdueopportunitiesdigest"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def load_flow(prefix):
    (path,) = (SOLUTION / "Workflows").glob(f"{prefix}-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))
