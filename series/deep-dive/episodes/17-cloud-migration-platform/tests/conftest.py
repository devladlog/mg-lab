import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cmdb_path():
    return ROOT / "data" / "contoso-cmdb.json"


@pytest.fixture()
def cmdb(cmdb_path):
    from migplan import inventory
    return inventory.load(cmdb_path)


@pytest.fixture()
def raw_cmdb(cmdb_path):
    return json.loads(cmdb_path.read_text(encoding="utf-8"))
