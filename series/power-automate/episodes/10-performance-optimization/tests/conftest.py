import copy
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FAST = next((SRC / "solution" / "Workflows").glob("*.json"))
SLOW = SRC / "drafts" / "slow-archive-done-requests.json"

needs_pac = pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")


@pytest.fixture
def fast():
    return json.loads(FAST.read_text())


@pytest.fixture
def slow():
    return json.loads(SLOW.read_text())


def actions(flow):
    return flow["properties"]["definition"]["actions"]


def loop_of(flow):
    a = actions(flow)
    return a["Apply_to_each"] if "Apply_to_each" in a else a["Any_to_archive"]["actions"]["Apply_to_each"]


def codes(findings, level=None):
    return sorted({f.code for f in findings if level is None or f.level == level})


def clone(flow):
    return copy.deepcopy(flow)
