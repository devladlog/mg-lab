import json
import pathlib
import sys

import pytest

EP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EP / "src"))

FIXTURES = EP / "tests" / "fixtures"


@pytest.fixture
def whatif():
    return lambda name: json.loads((FIXTURES / f"whatif-{name}.json").read_text())


@pytest.fixture
def policy():
    from whatif_gate import Policy
    return Policy.from_dict(json.loads((EP / "pipelines" / "gate-policy.json").read_text()))
