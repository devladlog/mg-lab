import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SOLUTION = SRC / "solution"
SAMPLES = SRC / "samples"
DESKTOP = SRC / "desktop-flow"
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def mocks(**override):
    m = sample("mocks-saved.json")
    m.update(override)
    return m


@pytest.fixture
def flow():
    (path,) = (SOLUTION / "Workflows").glob("Enterapprovedpurchaseorders-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.fixture
def contract():
    return json.loads((DESKTOP / "enter-purchase-order.contract.json").read_text(encoding="utf-8"))


@pytest.fixture
def script_text():
    return (DESKTOP / "enter-purchase-order.robin.txt").read_text(encoding="utf-8")


@pytest.fixture
def item():
    return copy.deepcopy(sample("request-approved.json"))
