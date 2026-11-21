import json
import shutil
from pathlib import Path

import pytest

from excelfake import scenario

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
OFFICESCRIPT = ROOT / "src" / "officescript"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node (22.13+) runs the Office Script")


@pytest.fixture
def flow():
    return json.loads(scenario.FLOW_PATH.read_text(encoding="utf-8-sig"))


def actions(flow):
    return flow["properties"]["definition"]["actions"]
