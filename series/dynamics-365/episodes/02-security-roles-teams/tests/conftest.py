import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rolecheck import model as m  # noqa: E402

SAMPLE = ROOT / "sample" / "contoso-security.json"


@pytest.fixture
def raw():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def sm(raw):
    return m.from_dict(copy.deepcopy(raw))


@pytest.fixture
def uid(sm):
    def _uid(name):
        return next(u.id for u in sm.users.values() if u.name == name)
    return _uid
