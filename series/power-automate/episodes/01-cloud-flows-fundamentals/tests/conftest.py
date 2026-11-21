import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
SAMPLES = ROOT / "src" / "samples"
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)  # a Monday, 09:00 UTC


def load_workflow(prefix: str) -> dict:
    (path,) = (SOLUTION / "Workflows").glob(f"{prefix}-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def intake():
    return load_workflow("ITrequestintake")


@pytest.fixture
def digest():
    return load_workflow("ITrequestsdailydigest")
