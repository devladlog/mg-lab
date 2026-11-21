"""What a run costs: actions (Power Platform requests, Learn), SharePoint calls and the throttling floor they imply."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from flowkit.lint import load_flow
from flowkit.sim import Simulator

from .sharepoint import FakeList, make_list

# Learn, "Limits of automated, scheduled, and instant flows": Power Platform requests per 24 hours (transition period)
DAILY_ACTION_LIMITS = {"Low": 10_000, "Medium": 200_000, "High": 500_000}
SHAREPOINT_CALLS_PER_MINUTE = 600  # Learn, SharePoint connector: API calls per connection, 600 per 60 seconds
NOW = datetime(2026, 11, 23, 2, 0, tzinfo=timezone.utc)
SP = "shared_sharepointonline"


@dataclass
class Cost:
    name: str
    items: int
    to_archive: int
    actions: int            # the trigger plus every action run, loop iterations included
    sharepoint_calls: int
    archived: int
    status: str

    @property
    def throttle_floor_minutes(self) -> float:
        """The least time 600 calls per minute allows for this many SharePoint calls. Real runs take longer."""
        return self.sharepoint_calls / SHAREPOINT_CALLS_PER_MINUTE

    def over(self, profile: str = "Low") -> bool:
        return self.actions > DAILY_ACTION_LIMITS[profile]


def measure(flow: dict | str | Path, items: FakeList | int, name: str | None = None, **list_kwargs) -> Cost:
    """Dry-run the flow against a fake list and count. The paginated flag follows the flow's own Get items setting."""
    if not isinstance(flow, dict):
        name = name or Path(flow).stem
        flow = load_flow(flow)
    lst = items if isinstance(items, FakeList) else make_list(items, **list_kwargs)
    n, expected = len(lst.items), sum(1 for i in lst.items if i["Status"]["Value"] == "Done" and i["DoneOn"] and i["DoneOn"] < "2026-10-24T02:00:00Z")
    paginated = {nm: bool((a.get("runtimeConfiguration") or {}).get("paginationPolicy"))
                 for nm, a in flow["properties"]["definition"]["actions"].items()}
    mocks = {
        "Get_all_requests": lambda i: lst.get_items(i, paginated["Get_all_requests"]),
        "Get_done_requests": lambda i: lst.get_items(i, paginated.get("Get_done_requests", True)),
        "Get_item_again": lst.get_item,
        "Archive_item": lst.patch_item,
        "Send_summary": lambda i: {"status": "Succeeded", "body": {}},
    }
    sim = Simulator(flow, mocks=mocks, now=NOW)
    result = sim.run({})
    sp_calls = sum(1 for _, r in result.history if isinstance(r.inputs, dict) and (r.inputs.get("host") or {}).get("connectionName") == SP)
    return Cost(name or "flow", n, expected, result.executions + 1, sp_calls, lst.calls.patch_item, result.status)
