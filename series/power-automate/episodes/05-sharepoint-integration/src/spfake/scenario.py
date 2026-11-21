"""The Purchasing site from episodes 2 and 3, plus the Orders library, and a poller that plays the
"When an item or a file is modified" trigger against it: each poll runs the flow once per changed item,
and whatever the flow writes back becomes a change the next poll sees (which is how loops happen)."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from flowkit import RunResult, Simulator
from flowkit.lint import definition_of, iter_actions

from .site import Site, SPList

SITE_URL = "https://contoso.sharepoint.com/sites/Purchasing"
PARAMS = {"Purchasing site URL (cts_PurchasingSiteUrl)": SITE_URL,
          "Orders library path (cts_OrdersLibraryPath)": "/sites/Purchasing/Orders"}


def purchasing_site() -> Site:
    site = Site(SITE_URL)
    site.add_list(SPList(
        title="Purchase Requests", url_name="PurchaseRequests",
        columns={"Title": "text", "Amount": "number", "Justification": "text", "Status": "choice",
                 "DecisionBy": "text", "DecisionComments": "text", "OrderFolder": "text"},
        required=("Title", "Amount"), versioning=True, next_id=itertools.count(41)))
    site.add_list(SPList(
        title="Orders", url_name="Orders", library=True,
        columns={"RequestId": "number", "RequestAmount": "number"}, versioning=True))
    site.add_site_group("Purchasing Owners", "Full Control")
    site.add_site_group("Purchasing Members", "Edit")
    for email, name in [("alex.demo@contoso.com", "Alex Demo"), ("jordan.demo@contoso.com", "Jordan Demo"),
                        ("sam.demo@contoso.com", "Sam Demo"), ("labadmin@contoso.com", "Lab Admin")]:
        site.add_user(email, name)
    return site


def user(site: Site, email: str) -> dict:
    return site.directory[f"i:0#.f|membership|{email}"]


@dataclass
class Poller:
    """Polls the trigger's list and runs the flow for every changed item (the trigger splits on body/value)."""
    site: Site
    flow: dict
    params: dict = field(default_factory=lambda: dict(PARAMS))
    mail: list = field(default_factory=list)
    runs: list = field(default_factory=list)          # (poll number, item id, RunResult)
    polls: int = 0

    def __post_init__(self):
        d = definition_of(self.flow)
        (self.trigger,) = d["triggers"].values()
        self.list_title = self.trigger["inputs"]["parameters"]["table"]
        self.mocks = {}
        for name, action, *_ in iter_actions(d.get("actions", {})):
            host = (action.get("inputs") or {}).get("host", {}) if isinstance(action.get("inputs"), dict) else {}
            api = host.get("apiId", "")
            if api.endswith("/shared_sharepointonline"):
                self.mocks[name] = self.site.connector
            elif api.endswith("/shared_office365"):
                self.mocks[name] = self._send_mail

    def _send_mail(self, inputs):
        p = inputs["parameters"]
        self.mail.append({"to": p.get("emailMessage/To"), "subject": p.get("emailMessage/Subject"),
                          "body": p.get("emailMessage/Body"), "importance": p.get("emailMessage/Importance")})
        return {"status": "Succeeded", "body": {}}

    def poll(self) -> list[RunResult]:
        self.polls += 1
        results = []
        for body in self.site.poll_modified(self.list_title):
            r = Simulator(self.flow, mocks=self.mocks, now=self.site.clock, parameters=self.params).run(body)
            self.runs.append((self.polls, body["ID"], r))
            results.append(r)
        self.site.tick(5)          # SharePoint triggers poll; the next check is a few minutes later
        return results

    def poll_until_quiet(self, max_polls: int = 10) -> int:
        """Poll until a poll finds nothing to run. Returns how many polls produced runs."""
        busy = 0
        for _ in range(max_polls):
            ran = [r for r in self.poll() if r.status != "Skipped"]
            if not ran:
                return busy
            busy += 1
        return busy

    def started_runs(self) -> list:
        return [(p, i, r) for p, i, r in self.runs if r.status != "Skipped"]


def first_version(flow: dict) -> dict:
    """Our first draft: the folder steps ran on every approved item, with no 'Needs order folder' check.
    Kept as a function so the loop it causes is reproducible (tests and `python -m spfake --first-version`)."""
    import copy
    f = copy.deepcopy(flow)
    acts = definition_of(f)["actions"]
    block = acts.pop("Needs_order_folder")["actions"]
    for name, action in block.items():
        if not action.get("runAfter"):
            action["runAfter"] = {"PR_reference": ["Succeeded"]}
        acts[name] = action
    acts["Amount_changed_after_approval"]["runAfter"] = {"Tell_requester": ["Succeeded"]}
    return f
