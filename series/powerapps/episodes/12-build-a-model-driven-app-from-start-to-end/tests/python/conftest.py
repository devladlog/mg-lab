import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[2]
SRC = EPISODE / "src"
SOLUTION = SRC / "solution"
SCHEMA_FILE = SRC / "schema" / "contosoinspections.schema.json"
sys.path.insert(0, str(SRC / "schema"))
sys.path.insert(0, str(SRC / "logic"))


class Result:
    def __init__(self, p):
        self.code, self.out, self.err = p.returncode, p.stdout, p.stderr

    def __repr__(self):
        return f"exit {self.code}\n{self.out}\n{self.err}"


def pac(*args):
    return Result(subprocess.run(["pac", *map(str, args)], capture_output=True, text=True, timeout=300))


@pytest.fixture(scope="session")
def schema():
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def model(schema):
    import build_solution
    return build_solution.Model(schema)


@pytest.fixture(scope="session")
def fresh_full(tmp_path_factory):
    """The solution source regenerated from the schema file right now (build_solution.py + pac solution unpack)."""
    import build_solution
    out = tmp_path_factory.mktemp("fresh") / "full"
    build_solution.main(["--profile", "full", "--out", str(out)])
    return out


def has_pac():
    return shutil.which("pac") is not None
