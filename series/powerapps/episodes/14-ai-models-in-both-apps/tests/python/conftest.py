import json
import subprocess
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[2]
SRC = EPISODE / "src"
EPISODES = EPISODE.parent
sys.path.insert(0, str(SRC / "eval"))
sys.path.insert(0, str(SRC / "solution"))
sys.path.insert(0, str(SRC / "flows"))
sys.path.insert(0, str(SRC / "app"))
sys.path.insert(0, str(SRC / "custompage"))


@pytest.fixture(scope="session")
def schema():
    return json.loads((SRC / "schema" / "contosoinspections.schema.json").read_text(encoding="utf-8"))


def pac(*args):
    p = subprocess.run(["pac", *map(str, args)], capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr
