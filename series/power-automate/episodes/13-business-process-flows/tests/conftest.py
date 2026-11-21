import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bpfkit.model import Process

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SOLUTION = SRC / "solution"
SAMPLES = SRC / "samples"
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
PROCESS_FILE = SRC / "process" / "purchase-request-process.json"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def load_flow(prefix):
    (path,) = (SOLUTION / "Workflows").glob(f"{prefix}-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.fixture
def definition():
    return json.loads(PROCESS_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def process(definition):
    return Process.from_dict(copy.deepcopy(definition))
