import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
SAMPLES = ROOT / "src" / "samples"
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
OK = {"status": "Succeeded", "body": {}}


def sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


RESPONSES = sample("approval-responses.json")


@pytest.fixture
def approval_flow():
    (path,) = (SOLUTION / "Workflows").glob("Purchaserequestapproval-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def actions(flow):
    return flow["properties"]["definition"]["actions"]


def finance_block(flow):
    return actions(flow)["Is_small_amount"]["else"]["actions"]["Needs_finance_approval"]["actions"]


def mocks(manager=None, finance=None, get_manager=None, **extra):
    """Mocks for every connector action; pass the approval replies you want to test."""
    m = {
        "Get_manager": get_manager or {"status": "Succeeded", "body": sample("manager.json")},
        "Manager_approval": manager or {"status": "Succeeded", "body": RESPONSES["manager_approves"]},
        "Finance_approval": finance or {"status": "Succeeded", "body": RESPONSES["finance_approves"]},
    }
    for name in ("Mark_approved", "Notify_requester_approved", "Mark_rejected", "Notify_requester_rejected",
                 "Mark_escalated", "Notify_purchasing_team"):
        m[name] = OK
    m.update(extra)
    return m


def approved(name):
    return {"status": "Succeeded", "body": RESPONSES[name]}


TIMED_OUT = {"status": "TimedOut"}
