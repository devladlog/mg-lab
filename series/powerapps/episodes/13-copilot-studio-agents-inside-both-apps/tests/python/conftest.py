import json
import subprocess
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[2]
SRC = EPISODE / "src"
EPISODES = EPISODE.parent
sys.path.insert(0, str(SRC / "scripts"))


@pytest.fixture(scope="session")
def schema():
    return json.loads((SRC / "schema" / "contosoinspections.schema.json").read_text(encoding="utf-8"))


def table(schema, logical):
    return next(t for t in schema["tables"] if t["logicalName"] == logical)


def column(schema, tname, cname):
    return next(c for c in table(schema, tname)["columns"] if c["logicalName"] == cname)


def pac(*args):
    p = subprocess.run(["pac", *map(str, args)], capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def pwsh(*args):
    p = subprocess.run(["pwsh", "-NoProfile", *map(str, args)], capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr
