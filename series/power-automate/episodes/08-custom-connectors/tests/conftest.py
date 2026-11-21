import copy
import json
from pathlib import Path

import pytest

from connectorkit import Connector, load_connector
from flowkit import load_flow
from githubfake import scenario

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
CONNECTOR = ROOT / "src" / "connector"


@pytest.fixture
def connector():
    return load_connector(CONNECTOR)


@pytest.fixture
def flow():
    return load_flow(scenario.FLOW_PATH)


@pytest.fixture
def world():
    return scenario.make_world()


def mutate(c: Connector, fn) -> Connector:
    d, p = copy.deepcopy(c.definition), copy.deepcopy(c.properties)
    fn(d, p)
    return Connector(d, p, dict(c.settings), len(json.dumps(d).encode()))
