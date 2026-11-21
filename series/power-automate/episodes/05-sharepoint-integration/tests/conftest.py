import json
from pathlib import Path

import pytest

from spfake import Poller, purchasing_site, user

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "src" / "solution"
REQUESTS = "Purchase Requests"


@pytest.fixture
def flow():
    (path,) = (SOLUTION / "Workflows").glob("Purchaseorderfolder-*.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def actions(flow):
    return flow["properties"]["definition"]["actions"]


def folder_block(flow):
    return actions(flow)["Needs_order_folder"]["actions"]


class Lab:
    """The Purchasing site, Alex's request, and a poller for the flow under test."""

    def __init__(self, flow, amount=12500, title="Laptops for two new developers"):
        self.site = purchasing_site()
        self.alex = user(self.site, "alex.demo@contoso.com")
        self.jordan = user(self.site, "jordan.demo@contoso.com")
        self.item = self.site.create_item(REQUESTS, {"Title": title, "Amount": amount, "Status": "Pending",
                                                     "Justification": "Two developer laptops, 32 GB RAM"}, self.alex)
        self.poller = Poller(self.site, flow)
        self.poller.poll()                       # the creation: "When an item or a file is modified" ignores it

    def approve(self, by="Jordan Demo"):
        # Episode 2's approval flow writes the decision with its own SharePoint connection.
        self.site.edit_item(REQUESTS, self.item, {"Status": "Approved", "DecisionBy": by}, self.site.connection_user)

    def edit(self, who, **changes):
        self.site.edit_item(REQUESTS, self.item, changes, who)

    @property
    def fields(self):
        return self.site.lists[REQUESTS].items[self.item].current

    @property
    def reference(self):
        return f"PR-{self.item:05d}"


@pytest.fixture
def lab(flow):
    return Lab(flow)


def ran(result, name):
    return result.status_of(name) == "Succeeded"
