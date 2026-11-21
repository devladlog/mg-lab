"""Contoso IT: a new GitHub issue in the it-automation repository becomes an IT request.

The pieces, wired like the real thing (everything except GitHub's and the platform's behaviour is the real file):
  connector/*.json            -> connectorkit.Runtime builds the requests exactly as the definition says
  GitHub (githubfake.server)  -> api.github.com: hooks, ping, issues events, comments, auth, User-Agent
  Platform (below)            -> what Power Automate does for a webhook trigger: subscribe when the flow is turned on,
                                 receive the callback, apply the trigger condition, run the flow, unsubscribe when it
                                 is turned off. This part is OUR MODEL of the documented behaviour (Learn).
  solution/Workflows/*.json   -> the real flow, run by flowkit.Simulator; SharePoint is a mock, the custom connector
                                 action goes through connectorkit.Runtime to the fake GitHub.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs

from connectorkit import Connection, Connector, Runtime, load_connector
from connectorkit.runtime import InputError, Subscription
from flowkit import RunResult, Simulator, load_flow

from .server import GitHub

ROOT = Path(__file__).resolve().parents[1]
CONNECTOR_DIR = ROOT / "connector"
FLOW_PATH = next((ROOT / "solution" / "Workflows").glob("GitHubissuetoITrequest-*.json"))
REPO = "contoso/it-automation"
OWNER, NAME = REPO.split("/")
CALLBACK = "https://flow.example.com/callbacks/00000000000000000000000000000801"
SITE = "https://contoso.sharepoint.com/sites/ITHelpdesk"
FULL = {"webhooks:write", "webhooks:read", "issues:write"}


@dataclass
class SharePoint:
    items: list = field(default_factory=list)

    def create_item(self, p: dict) -> dict:
        title = p.get("item/Title", "")
        if len(title) > 255:
            raise ValueError("Title is longer than 255 characters")
        n = len(self.items) + 41    # IT Requests already has #1..#40 from the other episodes
        item = {"ID": n, "Title": title, "Priority": p.get("item/Priority/Value"), "Status": p.get("item/Status/Value"),
                "Category": p.get("item/Category/Value"), "SourceLink": p.get("item/SourceLink"),
                "{Link}": f"{SITE}/Lists/IT%20Requests/DispForm.aspx?ID={n}"}
        self.items.append(item)
        return item


class Platform:
    """Power Automate's side of a webhook trigger (a model of what Learn documents)."""

    def __init__(self, runtime: Runtime, gh: GitHub, flow: dict, conn: Connection, sharepoint: SharePoint):
        self.rt, self.gh, self.flow, self.conn, self.sp = runtime, gh, flow, conn, sharepoint
        self.sub: Subscription | None = None
        self.runs: list[RunResult] = []
        self.ignored = 0              # callbacks the trigger condition filtered out (no run)
        self.received: list[tuple[str, dict]] = []   # (event header, body the trigger saw)

    def turn_on(self, owner=OWNER, repo=NAME) -> Subscription:
        self.gh.listen(CALLBACK, self.receive)
        self.sub = self.rt.subscribe("WhenAnIssueIsOpened", {"owner": owner, "repo": repo}, self.conn, CALLBACK)
        return self.sub

    def turn_off(self):
        """Turning the flow off or deleting it: the platform removes the webhook through the delete operation."""
        res = self.rt.unsubscribe(self.sub, self.conn) if self.sub else None
        self.gh.callbacks.pop(CALLBACK, None)
        return res

    def receive(self, headers: dict, raw: str) -> int:
        if headers["content-type"].startswith("application/json"):
            body = json.loads(raw)
        else:   # a form post: the JSON is in the field `payload`, so the trigger sees no `action` or `issue`
            body = {"payload": parse_qs(raw)["payload"][0]}
        self.received.append((headers["x-github-event"], body))
        run = Simulator(self.flow, mocks=self._mocks()).run(body)
        if run.status == "Skipped":
            self.ignored += 1
        else:
            self.runs.append(run)
        return 200

    # ---- the actions' connectors
    def _mocks(self):
        def create_item(inputs):
            try:
                return {"status": "Succeeded", "body": self.sp.create_item(inputs["parameters"])}
            except ValueError as e:
                return {"status": "Failed", "statusCode": 400, "body": {"message": str(e)}, "error": str(e)}

        def comment(inputs):
            p = inputs["parameters"]
            try:
                res = self.rt.invoke("AddIssueComment", {"owner": p.get("owner"), "repo": p.get("repo"),
                                                         "issue_number": p.get("issue_number"),
                                                         "body": {"body": p.get("body/body")}}, self.conn)
            except InputError as e:
                return {"status": "Failed", "statusCode": 400, "body": {"message": str(e)}, "error": str(e)}
            if res.status >= 300:
                return {"status": "Failed", "statusCode": res.status, "body": res.body, "error": (res.body or {}).get("message")}
            return {"status": "Succeeded", "statusCode": res.status, "body": res.body}

        return {"Create_IT_request": create_item, "Comment_on_issue": comment}


@dataclass
class World:
    gh: GitHub
    rt: Runtime
    platform: Platform
    sharepoint: SharePoint
    connector: Connector


def make_world(connector: Connector | None = None, flow: dict | None = None, send_location: bool = True,
               permissions=FULL, token="ghp_demo_0000", user="contoso-it-bot") -> World:
    gh = GitHub(send_location=send_location)
    gh.add_repo(REPO)
    gh.add_token(user, token, {REPO}, set(permissions))
    c = connector or load_connector(CONNECTOR_DIR)
    rt = Runtime(c, gh.handle)
    sp = SharePoint()
    platform = Platform(rt, gh, flow or load_flow(FLOW_PATH), Connection(user, token), sp)
    return World(gh, rt, platform, sp, c)


def describe(w: World) -> str:
    lines = []
    sub = w.platform.sub
    if sub is not None:
        lines.append(f"webhook: POST {sub.created.status}, events {sub.created.body.get('events')}, "
                     f"content_type {sub.created.body['config']['content_type']}, Location {sub.location}")
    for d in w.gh.deliveries:
        lines.append(f"delivery: {d.event:<6} {d.action or '':<8} {d.content_type:<33} -> {d.status}")
    lines.append(f"flow runs: {[r.status for r in w.platform.runs]}   callbacks ignored by the trigger condition: {w.platform.ignored}")
    for it in w.sharepoint.items:
        lines.append(f"IT request #{it['ID']}: {it['Title']!r} priority {it['Priority']}")
    for n, issue in w.gh.issues.get(REPO, {}).items():
        for user, text in issue.comments:
            lines.append(f"comment on issue #{n} by {user}: {text}")
    for r in w.platform.runs:
        for name, res in r.actions.items():
            if res.status == "Failed":
                lines.append(f"  {name} failed: {res.error}")
    lines.append(f"webhooks left on GitHub: {len(w.gh.hooks)}")
    return "\n".join(lines)
