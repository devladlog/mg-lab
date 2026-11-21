import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from flowkit.timefmt import parse_timestamp

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
SAMPLES = ROOT / "src" / "samples"

# The flow runs on Mondays at 07:00 Lisbon time.
SUMMER_RUN = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)   # 07:00 WEST (UTC+1)
WINTER_RUN = datetime(2026, 1, 12, 7, 0, tzinfo=timezone.utc)   # 07:00 WET (UTC+0)
OK = {"status": "Succeeded", "body": {}}


def sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.fixture
def digest():
    (path,) = (SOLUTION / "Workflows").glob("Weeklypurchasingdigest-*.json")
    return load(path)


def actions(flow):
    return flow["properties"]["definition"]["actions"]


_WINDOW = re.compile(r"^Created ge '([^']+)' and Created lt '([^']+)'$")


def fake_sharepoint(items):
    """A Get items mock that applies the flow's OData date window, like SharePoint would."""
    def get_items(inputs):
        m = _WINDOW.match(inputs["parameters"]["$filter"])
        assert m, f"unexpected $filter: {inputs['parameters']['$filter']!r}"
        start, end = (parse_timestamp(x) for x in m.groups())
        kept = [i for i in items if start <= parse_timestamp(i["Created"]) < end]
        return {"status": "Succeeded", "body": {"value": kept}}
    return get_items


def mocks(items=None, sent=None):
    """Mocks for both connector actions; 'sent' collects the email inputs."""
    items = sample("purchase-requests.json")["value"] if items is None else items

    def send(inputs):
        if sent is not None:
            sent.append(inputs["parameters"])
        return OK
    return {"Get_requests": fake_sharepoint(items), "Send_digest": send}
