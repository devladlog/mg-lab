"""Execute an HTTP action for real, against a local server, with the documented retry behaviour.

What this follows (Learn):
* A retry policy resends the request when it "times out or fails, resulting in a 408, 429, or 5xx
  response". Other 4xx responses fail at once.  (Handle workflow errors and exceptions)
* "To specify the number of seconds between retry attempts, you can add the Retry-After header to the
  HTTP action response."  (Call external HTTP or HTTPS endpoints)
* Policy types default / none / fixed / exponential; count 1-90; intervals PT5S to P1D.
* Power Automate's default policy: Medium/High profiles "up to 12 retries at exponentially increasing
  intervals, which scale by seven (7) seconds up to an interval of approximately 1 hour".  (Limits page)
* Active Directory OAuth: authority (optional), tenant, audience, clientId, secret.

What is a flowkit simplification (not the engine):
* Exponential intervals are deterministic: min(maximumInterval, max(minimumInterval, interval * 2^(n-1))).
  The engine picks a random interval from a growing range.
* The default policy is modelled as 12 retries of 7 s * 2^(n-1), capped at 1 hour.
* The OAuth token is fetched with a standard client-credentials POST to {authority}/{tenant}/oauth2/v2.0/token
  with scope '{audience}/.default'. The engine does this internally; how exactly isn't documented.
* Only hosts in `allow_hosts` (127.0.0.1 and localhost by default) can be called, so a test can never
  reach a real service.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .lint import iso_duration_seconds

RETRY_STATUSES = {408, 429} | set(range(500, 600))
DEFAULT_POLICY = {"type": "default"}


class HttpCallError(Exception):
    """The call can't be made (host not allowed, bad inputs). The action fails with this message."""


@dataclass
class Attempt:
    status: int
    wait_after: float | None = None   # seconds waited before the next attempt (None: no retry)


@dataclass
class HttpOutcome:
    status_code: int
    headers: dict
    body: object
    attempts: list[Attempt] = field(default_factory=list)


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never use a proxy: local calls only


def _send(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, dict, object]:
    req = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            status, hdrs, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        status, hdrs, raw = e.code, dict(e.headers), e.read()
    text = raw.decode("utf-8", errors="replace")
    ctype = next((v for k, v in hdrs.items() if k.lower() == "content-type"), "")
    if "json" in ctype and text:
        try:
            return status, hdrs, json.loads(text)
        except json.JSONDecodeError:
            pass
    return status, hdrs, text


def policy_waits(policy: dict | None) -> Callable[[int], float] | None:
    """Return f(retry_number) -> seconds, or None for 'none'. retry_number starts at 1."""
    policy = policy or DEFAULT_POLICY
    kind = str(policy.get("type", "default")).lower()
    if kind == "none":
        return None
    if kind == "default":
        return lambda n: min(3600.0, 7.0 * 2 ** (n - 1)) if n <= 12 else -1
    count = int(policy.get("count", 0))
    interval = iso_duration_seconds(policy["interval"])
    if kind == "fixed":
        return lambda n: interval if n <= count else -1
    if kind == "exponential":
        lo = iso_duration_seconds(policy.get("minimumInterval", "PT5S"))
        hi = iso_duration_seconds(policy.get("maximumInterval", "P1D"))
        return lambda n: min(hi, max(lo, interval * 2 ** (n - 1))) if n <= count else -1
    raise HttpCallError(f"unknown retry policy type {policy.get('type')!r}")


class HttpClient:
    def __init__(self, sleep: Callable[[float], None], allow_hosts=("127.0.0.1", "localhost"), timeout: float = 10.0):
        self.sleep = sleep
        self.allow_hosts = set(allow_hosts)
        self.timeout = timeout
        self._tokens: dict[tuple, str] = {}

    def _check_host(self, url: str):
        host = urllib.parse.urlsplit(url).hostname
        if host not in self.allow_hosts:
            raise HttpCallError(f"flowkit only calls local test servers; {host!r} isn't in allow_hosts {sorted(self.allow_hosts)}")

    def _authorization(self, auth: dict | None) -> tuple[str | None, HttpOutcome | None]:
        if not auth:
            return None, None
        kind = auth.get("type")
        if kind == "Basic":
            raw = f"{auth['username']}:{auth['password']}".encode()
            return "Basic " + base64.b64encode(raw).decode(), None
        if kind == "Raw":
            return auth["value"], None
        if kind == "ActiveDirectoryOAuth":
            authority = (auth.get("authority") or "https://login.microsoftonline.com").rstrip("/")
            key = (authority, auth["tenant"], auth["clientId"], auth["audience"])
            if key not in self._tokens:
                url = f"{authority}/{auth['tenant']}/oauth2/v2.0/token"
                self._check_host(url)
                form = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": auth["clientId"],
                                               "client_secret": auth.get("secret") or "",
                                               "scope": auth["audience"].rstrip("/") + "/.default"}).encode()
                status, headers, body = _send("POST", url, {"Content-Type": "application/x-www-form-urlencoded"},
                                              form, self.timeout)
                if status != 200 or not isinstance(body, dict) or "access_token" not in body:
                    return None, HttpOutcome(status, headers, body, [Attempt(status)])
                self._tokens[key] = body["access_token"]
            return "Bearer " + self._tokens[key], None
        raise HttpCallError(f"authentication type {kind!r} isn't supported by flowkit")

    def call(self, inputs: dict) -> HttpOutcome:
        method = inputs.get("method", "GET")
        url = inputs["uri"]
        query = inputs.get("queries") or {}
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
        self._check_host(url)
        headers = {str(k): str(v) for k, v in (inputs.get("headers") or {}).items()}
        authz, failed = self._authorization(inputs.get("authentication"))
        if failed:
            return failed  # the token request failed: no call to the API, no retry
        if authz:
            headers["Authorization"] = authz
        body = inputs.get("body")
        data = None
        if body is not None:
            data = (json.dumps(body) if not isinstance(body, str) else body).encode()
            headers.setdefault("Content-Type", "application/json")
        waits = policy_waits(inputs.get("retryPolicy"))
        attempts: list[Attempt] = []
        n = 0
        while True:
            status, resp_headers, resp_body = _send(method, url, headers, data, self.timeout)
            attempt = Attempt(status)
            attempts.append(attempt)
            if status not in RETRY_STATUSES or waits is None:
                break
            n += 1
            wait = waits(n)
            if wait < 0:
                break  # retries exhausted
            retry_after = next((v for k, v in resp_headers.items() if k.lower() == "retry-after"), None)
            if retry_after is not None and str(retry_after).strip().isdigit():
                wait = float(retry_after)
            attempt.wait_after = wait
            self.sleep(wait)
        return HttpOutcome(status, resp_headers, resp_body, attempts)
