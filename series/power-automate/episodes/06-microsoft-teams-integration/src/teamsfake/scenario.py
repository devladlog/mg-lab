"""The IT Helpdesk from episode 1 plus the IT on-call team, and a harness that runs the dispatch flow
for a new IT request with a scripted answer on the card."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from flowkit import RunResult, Simulator
from flowkit.lint import definition_of, iter_actions

from .teams import Response, Teams

TEAM_ID = "00000000-0000-0000-0000-000000000601"
ONCALL_CHANNEL = "19:00000000000000000000000000000601@thread.tacv2"
PRIVATE_CHANNEL = "19:00000000000000000000000000000602@thread.tacv2"
SITE_URL = "https://contoso.sharepoint.com/sites/ITHelpdesk"
PARAMS = {"IT Helpdesk site URL (cts_HelpdeskSiteUrl)": SITE_URL,
          "On-call team ID (cts_OnCallTeamId)": TEAM_ID,
          "On-call channel ID (cts_OnCallChannelId)": ONCALL_CHANNEL,
          "On-call lead (cts_OnCallLeadUpn)": "taylor.demo@contoso.com"}
USERS = {"alex.demo@contoso.com": "Alex Demo", "sam.demo@contoso.com": "Sam Demo",
         "riley.demo@contoso.com": "Riley Demo", "taylor.demo@contoso.com": "Taylor Demo",
         "jordan.demo@contoso.com": "Jordan Demo"}


def it_request(item_id=42, title="Laptop won't boot before a client demo", priority="High",
               category="Hardware", author="alex.demo@contoso.com", created="2026-01-05T08:58:12Z") -> dict:
    """A SharePoint-shaped IT Requests item, as the 'When an item is created' trigger returns it."""
    return {"@odata.etag": "\"1\"", "ItemInternalId": str(item_id), "ID": item_id, "Title": title,
            "Category": {"Value": category}, "Priority": {"Value": priority}, "Status": {"Value": "New"},
            "AssignedTo": None, "Created": created,
            "Author": {"Claims": f"i:0#.f|membership|{author}", "DisplayName": USERS.get(author, author),
                       "Email": author},
            "{Link}": f"{SITE_URL}/Lists/IT%20Requests/DispForm.aspx?ID={item_id}"}


@dataclass
class Helpdesk:
    """The IT Requests list, just enough for Update item: Title is required (episode 1's list)."""
    updates: list = field(default_factory=list)

    def connector(self, inputs):
        p = inputs["parameters"]
        if inputs["host"]["operationId"] != "PatchItem":
            raise NotImplementedError(inputs["host"]["operationId"])
        if p.get("dataset") != SITE_URL or p.get("table") != "IT Requests":
            return {"status": "Failed", "statusCode": 404, "error": "404: list not found", "body": {}}
        if not p.get("item/Title"):
            return {"status": "Failed", "statusCode": 400, "error": "400: Required column missing: Title", "body": {}}
        self.updates.append(p)
        return {"status": "Succeeded", "statusCode": 200, "body": {"ID": p["id"]}}


class Dispatch:
    """Runs the flow once per new request. Mocks: Teams actions -> Teams fake, SharePoint -> Helpdesk."""

    def __init__(self, flow: dict, teams: Teams | None = None):
        self.flow = flow
        self.teams = teams or default_teams()
        self.helpdesk = Helpdesk()
        self.params = dict(PARAMS)
        self.mocks = {}
        for name, action, *_ in iter_actions(definition_of(flow).get("actions", {})):
            inputs = action.get("inputs") if isinstance(action.get("inputs"), dict) else {}
            api = (inputs.get("host") or {}).get("apiId", "")
            if api.endswith("/shared_teams"):
                self.mocks[name] = self.teams.connector
            elif api.endswith("/shared_sharepointonline"):
                self.mocks[name] = self.helpdesk.connector

    def run(self, item: dict, answer: Response | None = None) -> RunResult:
        if answer is not None:
            self.teams.responses.append(answer)
        return Simulator(self.flow, mocks=self.mocks, now=self.teams.clock, parameters=self.params).run(item)

    @property
    def channel(self):
        return self.teams.channels[(TEAM_ID, ONCALL_CHANNEL)]


def default_teams() -> Teams:
    t = Teams()
    t.add_channel(TEAM_ID, ONCALL_CHANNEL, "On-call")
    t.add_channel(TEAM_ID, PRIVATE_CHANNEL, "Leads (private)", private=True)
    for upn, name in USERS.items():
        t.add_user(upn, name)
    return t
