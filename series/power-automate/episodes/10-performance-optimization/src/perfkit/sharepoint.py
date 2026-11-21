"""A fake SharePoint list for the tests (NOT used in the demo): just enough of Get items / Get item / Update item
to run the draft and the tuned flow and count what they cost.

Modelled from Learn: Get items returns the first 100 items by default and paginates; a filter needs indexed columns on lists over
the 5,000 item view threshold; with pagination off and no match in the first 5,000 items, a filtered Get items
returns nothing ("Known limitation"). The $filter grammar is only what our flows use; anything else raises."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VIEW_THRESHOLD = 5000
FILTER = re.compile(r"^Status (?P<op>eq|ne) '(?P<status>[^']+)'(?: and DoneOn lt '(?P<before>[^']+)')?$")


class ThrottledError(Exception):
    """The list view threshold: a filter on a column that isn't indexed, over a list of more than 5,000 items."""


@dataclass
class Calls:
    get_items: int = 0
    get_item: int = 0
    patch_item: int = 0

    @property
    def total(self) -> int:
        return self.get_items + self.get_item + self.patch_item


@dataclass
class FakeList:
    items: list[dict]
    indexed: set[str] = field(default_factory=lambda: {"Status", "DoneOn"})
    calls: Calls = field(default_factory=Calls)

    # ---- the three operations, as mocks for flowkit.sim: inputs -> {"status", "body"}
    def get_items(self, inputs: dict, paginated: bool = True) -> dict:
        self.calls.get_items += 1
        params = inputs["parameters"]
        flt = params.get("$filter")
        pool = self.items
        if flt:
            m = FILTER.match(flt)
            if not m:
                raise ValueError(f"the fake list doesn't understand $filter {flt!r}")
            cols = {"Status"} | ({"DoneOn"} if m["before"] else set())
            if len(self.items) > VIEW_THRESHOLD and not cols <= self.indexed:
                raise ThrottledError(f"filter on {sorted(cols - self.indexed)} exceeds the list view threshold")
            # Learn, known limitation: over 5,000 items and no pagination, only the first 5,000 are looked at
            scan = self.items if (paginated or len(self.items) <= VIEW_THRESHOLD) else self.items[:VIEW_THRESHOLD]
            pool = [i for i in scan if self._match(i, m)]
        top = int(params.get("$top") or 100)
        limit = max(top, 5000) if paginated else top  # paginated: up to the pagination threshold (5,000 here)
        return {"status": "Succeeded", "body": {"value": [dict(i) for i in pool[:limit]]}}

    def get_item(self, inputs: dict) -> dict:
        self.calls.get_item += 1
        item = next(i for i in self.items if i["ID"] == inputs["parameters"]["id"])
        return {"status": "Succeeded", "body": dict(item)}

    def patch_item(self, inputs: dict) -> dict:
        self.calls.patch_item += 1
        item = next(i for i in self.items if i["ID"] == inputs["parameters"]["id"])
        item["Status"] = {"Value": inputs["parameters"]["item/Status/Value"]}
        return {"status": "Succeeded", "body": dict(item)}

    @staticmethod
    def _match(item: dict, m: re.Match) -> bool:
        same = item["Status"]["Value"] == m["status"]
        if m["op"] == "ne":
            same = not same
        if m["before"]:
            same = same and item.get("DoneOn") is not None and item["DoneOn"] < m["before"]
        return same


def make_list(n: int, done_old_fraction: float = 0.4, now: datetime | None = None) -> FakeList:
    """n requests: `done_old_fraction` are Done for 31+ days, 10 % Done recently, the rest New or Triaged."""
    now = now or datetime(2026, 11, 23, 2, 0, tzinfo=timezone.utc)
    old = int(n * done_old_fraction)
    recent = int(n * 0.1)
    items = []
    for i in range(1, n + 1):
        if i <= old:
            status, done = "Done", (now - timedelta(days=31 + i % 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif i <= old + recent:
            status, done = "Done", (now - timedelta(days=1 + i % 20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            status, done = ("Triaged" if i % 2 else "New"), None
        items.append({"ID": i, "Title": f"[TEST] seed {i}", "Status": {"Value": status}, "DoneOn": done})
    return FakeList(items)
