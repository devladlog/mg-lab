import json
from pathlib import Path

import pytest

from teamsfake import Dispatch, Response, it_request

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
SAM, RILEY, TAYLOR = "sam.demo@contoso.com", "riley.demo@contoso.com", "taylor.demo@contoso.com"


@pytest.fixture
def flow():
    (path,) = (SOLUTION / "Workflows").glob("ITon-calldispatch-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.fixture
def dispatch(flow):
    return Dispatch(flow)


def actions(flow):
    return flow["properties"]["definition"]["actions"]




def card_sent(result):
    return json.loads(result.actions["Ask_on_call"].inputs["parameters"]["body/body/messageBody"])
