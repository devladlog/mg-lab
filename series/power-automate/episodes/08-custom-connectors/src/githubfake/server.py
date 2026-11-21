"""In-memory GitHub, for the tests only. Behaviour that comes from the docs (GitHub REST docs, Learn):

- every request needs a User-Agent header (403 without it) and valid credentials (401)
- POST /repos/{o}/{r}/hooks: needs the Webhooks (write) permission on the repository, else 404; defaults
  events ["push"], content_type "form", active true, insecure_ssl "0"; answers 201 and, as Learn requires for
  triggers, a Location header with the URL of the new hook; GitHub then sends a `ping` event to the hook
- content_type json: the payload is the body; form: the payload is sent as a form field called `payload`
- POST /repos/{o}/{r}/issues/{n}/comments: needs Issues (write), 201; 404 when the issue doesn't exist
- DELETE a hook: 204
The `issues` event has action, issue, repository, sender; `issue_comment` is a different event.
Not modelled: secondary rate limits, delivery retries and timeouts, hook secrets and signatures.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote, urlencode, urlparse

from connectorkit import Request, Response

API = "api.github.com"


@dataclass
class Token:
    user: str
    secret: str
    repos: set                       # "owner/repo"
    permissions: set                 # "webhooks:write", "webhooks:read", "issues:write"


@dataclass
class Hook:
    id: int
    repo: str
    events: list
    active: bool
    config: dict


@dataclass
class Issue:
    number: int
    title: str
    body: str
    user: str
    labels: list
    html_url: str
    comments: list = field(default_factory=list)


@dataclass
class Delivery:
    hook_id: int
    event: str
    action: str | None
    content_type: str
    status: int | None


Callback = Callable[[dict, str], int]    # (headers, raw body) -> HTTP status


class GitHub:
    def __init__(self, send_location: bool = True):
        self.send_location = send_location
        self.tokens: dict[tuple, Token] = {}
        self.repos: set[str] = set()
        self.hooks: dict[int, Hook] = {}
        self.issues: dict[str, dict[int, Issue]] = {}
        self.callbacks: dict[str, Callback] = {}      # callback URL -> receiver (the "flow")
        self.deliveries: list[Delivery] = []
        self.requests: list[Request] = []
        self._hook_seq, self._delivery_seq = 0, 0

    # ------------------------------------------------------------------ setup helpers
    def add_repo(self, full_name: str):
        self.repos.add(full_name)
        self.issues.setdefault(full_name, {})

    def add_token(self, user: str, secret: str, repos: set, permissions: set):
        self.tokens[(user, secret)] = Token(user, secret, set(repos), set(permissions))

    def listen(self, url: str, receiver: Callback):
        self.callbacks[url] = receiver

    # ------------------------------------------------------------------ the API
    def handle(self, req: Request) -> Response:
        self.requests.append(req)
        u = urlparse(req.url)
        if u.netloc != API:
            return Response(404, body={"message": "Not Found"})
        if not req.headers.get("user-agent"):
            return Response(403, body={"message": "Request forbidden by administrative rules. Please make sure your request has a User-Agent header."})
        token = self._auth(req)
        if token is None:
            return Response(401, body={"message": "Bad credentials"})
        parts = [p for p in u.path.split("/") if p]
        m = req.method
        if parts == ["user"] and m == "GET":
            return Response(200, body={"login": token.user, "id": 1000 + len(token.user)})
        if len(parts) >= 4 and parts[0] == "repos":
            repo = f"{parts[1]}/{parts[2]}"
            rest = parts[3:]
            if rest == ["hooks"] and m == "POST":
                return self._create_hook(token, repo, req)
            if len(rest) == 2 and rest[0] == "hooks" and m == "DELETE":
                return self._delete_hook(token, repo, rest[1])
            if len(rest) == 3 and rest[0] == "issues" and rest[2] == "comments" and m == "POST":
                return self._comment(token, repo, rest[1], req)
        return Response(404, body={"message": "Not Found"})

    def _auth(self, req: Request) -> Token | None:
        h = req.headers.get("authorization", "")
        if not h.startswith("Basic "):
            return None
        try:
            user, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except Exception:
            return None
        return self.tokens.get((user, secret))

    def _can(self, token: Token, repo: str, permission: str) -> bool:
        return repo in self.repos and repo in token.repos and permission in token.permissions

    def _create_hook(self, token, repo, req) -> Response:
        if not self._can(token, repo, "webhooks:write"):
            return Response(404, body={"message": "Not Found"})
        b = req.body if isinstance(req.body, dict) else {}
        config = b.get("config") or {}
        if not config.get("url"):
            return Response(422, body={"message": "Validation Failed", "errors": [{"resource": "Hook", "code": "custom", "message": "Config url can't be blank"}]})
        if b.get("name", "web") != "web":
            return Response(422, body={"message": "Validation Failed"})
        self._hook_seq += 1
        hook = Hook(self._hook_seq, repo, list(b.get("events") or ["push"]), b.get("active", True),
                    {"url": config["url"], "content_type": config.get("content_type", "form"),
                     "insecure_ssl": str(config.get("insecure_ssl", "0"))})
        self.hooks[hook.id] = hook
        self._deliver(hook, "ping", {"zen": "Keep it logically awesome.", "hook_id": hook.id,
                                     "hook": {"id": hook.id, "events": hook.events, "active": hook.active}}, None)
        headers = {"location": f"https://{API}/repos/{repo}/hooks/{hook.id}"} if self.send_location else {}
        return Response(201, headers, {"id": hook.id, "name": "web", "active": hook.active, "events": hook.events,
                                       "config": hook.config})

    def _delete_hook(self, token, repo, hook_id) -> Response:
        if not self._can(token, repo, "webhooks:write"):
            return Response(404, body={"message": "Not Found"})
        hook = self.hooks.get(int(hook_id)) if hook_id.isdigit() else None
        if hook is None or hook.repo != repo:
            return Response(404, body={"message": "Not Found"})
        del self.hooks[hook.id]
        return Response(204)

    def _comment(self, token, repo, number, req) -> Response:
        if repo in self.repos and repo in token.repos and "issues:write" not in token.permissions:
            return Response(403, body={"message": "Resource not accessible by personal access token"})
        if not self._can(token, repo, "issues:write"):
            return Response(404, body={"message": "Not Found"})
        issue = self.issues.get(repo, {}).get(int(number)) if number.isdigit() else None
        if issue is None:
            return Response(404, body={"message": "Not Found"})
        text = (req.body or {}).get("body") if isinstance(req.body, dict) else None
        if not isinstance(text, str) or not text:
            return Response(422, body={"message": "Validation Failed"})
        issue.comments.append((token.user, text))
        cid = 9000 + len(issue.comments)
        for hook in list(self.hooks.values()):
            if hook.repo == repo and hook.active and "issue_comment" in hook.events:
                self._deliver(hook, "issue_comment", {"action": "created", "issue": {"number": issue.number},
                                                       "comment": {"id": cid, "body": text}}, "created")
        return Response(201, body={"id": cid, "html_url": f"{issue.html_url}#issuecomment-{cid}"})

    # ------------------------------------------------------------------ what people do on github.com
    def open_issue(self, repo: str, title: str, body: str, user: str, labels=()) -> Issue:
        n = len(self.issues[repo]) + 1
        issue = Issue(n, title, body, user, list(labels), f"https://github.com/{repo}/issues/{n}")
        self.issues[repo][n] = issue
        self._issue_event(repo, issue, "opened", user)
        return issue

    def edit_issue(self, repo: str, number: int, title: str, user: str):
        issue = self.issues[repo][number]
        issue.title = title
        self._issue_event(repo, issue, "edited", user)

    def label_issue(self, repo: str, number: int, label: str, user: str):
        issue = self.issues[repo][number]
        issue.labels.append(label)
        self._issue_event(repo, issue, "labeled", user)

    def _issue_event(self, repo, issue, action, sender):
        payload = {"action": action,
                   "issue": {"number": issue.number, "title": issue.title, "body": issue.body,
                             "html_url": issue.html_url, "user": {"login": issue.user},
                             "labels": [{"name": n} for n in issue.labels]},
                   "repository": {"full_name": repo}, "sender": {"login": sender}}
        for hook in list(self.hooks.values()):
            if hook.repo == repo and hook.active and "issues" in hook.events:
                self._deliver(hook, "issues", payload, action)

    def _deliver(self, hook: Hook, event: str, payload: dict, action: str | None):
        self._delivery_seq += 1
        ctype = "application/json" if hook.config["content_type"] == "json" else "application/x-www-form-urlencoded"
        raw = json.dumps(payload) if ctype == "application/json" else urlencode({"payload": json.dumps(payload)}, quote_via=quote)
        headers = {"content-type": ctype, "x-github-event": event, "x-github-delivery": f"00000000-0000-0000-0000-{self._delivery_seq:012d}"}
        receiver = self.callbacks.get(hook.config["url"])
        status = receiver(headers, raw) if receiver else None
        self.deliveries.append(Delivery(hook.id, event, action, ctype, status))

    def deliveries_of(self, event: str) -> list[Delivery]:
        return [d for d in self.deliveries if d.event == event]
