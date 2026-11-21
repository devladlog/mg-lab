"""Business Central API v2.0 client (the local developer container from setup/New-LabBusinessCentral.ps1).

What Learn documents (Endpoints for the APIs, API endpoint structure, Tips for working with APIs, Server-driven paging,
Operational limits, Web services authentication):
- on-premises / container endpoint: https://<host>:<port>/<server instance>/api/v2.0 (the container here is plain http
  on 7048 unless it was created with -useSSL); all resources live under companies({id}), so the company id comes first
- the root URL lists the available APIs, companies is the first call
- on-premises basic authentication: the user name plus the web service access key as password, for NavUserPassword
  and AccessControlService servers (basic auth with access keys is deprecated in Business Central online: not used here)
- server-driven paging: Prefer: odata.maxpagesize=<n>, follow @odata.nextLink; the default maximum is 20,000
- 429 (too many requests) and 503 (queue timeout) are the throttling answers; Retry-After is honoured when present
"""
from __future__ import annotations

import base64
import time
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import quote

import requests


class BcError(Exception):
    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status, self.message, self.code = status, message, code


HINTS = {
    401: "check BC_USER and BC_PASSWORD (the container's admin user; if the password is refused, Learn says on-premises "
         "basic authentication takes the web service access key from the user card as the password)",
    403: "the user has no permission on this resource",
    404: "wrong server instance or company id? the default is <host>:7048/BC; run 'doctor' to see what answers",
    405: "Learn: on-premises, a call returns 405 when OData or API services are switched off on the server instance",
}


class BcApi:
    def __init__(self, base_url: str, user: str, password: str, *, api_version: str = "v2.0",
                 session: Optional[requests.Session] = None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = 60):
        self.root = f"{base_url.rstrip('/')}/api/{api_version}"
        self._auth = "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self.session = session or requests.Session()
        self.max_retries, self._sleep, self.timeout = max_retries, sleep, timeout

    # ---- URLs ------------------------------------------------------------------------------------------------
    def companies_url(self) -> str:
        return f"{self.root}/companies"

    def url(self, company_id: str, entity: str, *, select: Optional[List[str]] = None, filter: Optional[str] = None,
            orderby: Optional[str] = None, top: Optional[int] = None) -> str:
        parts = []
        if select:
            parts.append("$select=" + ",".join(select))
        if filter:
            parts.append("$filter=" + quote(filter, safe="=,()'"))
        if orderby:
            parts.append("$orderby=" + quote(orderby, safe=","))
        if top:
            parts.append(f"$top={top}")
        return f"{self.root}/companies({company_id})/{entity}" + ("?" + "&".join(parts) if parts else "")

    # ---- requests --------------------------------------------------------------------------------------------
    def request(self, method: str, url: str, *, body: Optional[Dict[str, Any]] = None,
                page_size: Optional[int] = None) -> Optional[Dict[str, Any]]:
        headers = {"Authorization": self._auth, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if page_size:
            headers["Prefer"] = f"odata.maxpagesize={page_size}"
        # a rejected request (429) is safe to repeat; a 503 only for reads, so a POST is never sent twice by accident
        retry_on = {429, 503} if method == "GET" else {429}
        for attempt in range(self.max_retries + 1):
            try:
                r = self.session.request(method, url, headers=headers, json=body, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                raise BcError(0, f"cannot reach {self.root}: {type(e).__name__}. Is the container running "
                                 "(docker ps) and does the host name resolve (-updateHosts)?") from e
            if r.status_code not in retry_on or attempt == self.max_retries:
                break
            self._sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
        if r.status_code >= 400:
            code, msg = "", ""
            try:
                err = r.json().get("error", {})
                code, msg = err.get("code", ""), err.get("message", "")
            except (ValueError, AttributeError):
                msg = (r.text or "")[:300]
            msg = msg or (r.text or "")[:300] or "no message"
            if r.status_code in HINTS:
                msg = f"{msg} ({HINTS[r.status_code]})"
            raise BcError(r.status_code, msg, code)
        if r.status_code == 204 or not r.text:
            return None
        return r.json()

    def get_all(self, url: str, page_size: int = 500, max_pages: int = 10000) -> Iterator[Dict[str, Any]]:
        nxt: Optional[str] = url
        seen = set()
        for _ in range(max_pages):
            if not nxt:
                return
            if nxt in seen:
                raise BcError(0, f"@odata.nextLink repeated ({nxt}): stopping instead of looping")
            seen.add(nxt)
            page = self.request("GET", nxt, page_size=page_size) or {}
            yield from page.get("value", [])
            nxt = page.get("@odata.nextLink")
        raise BcError(0, f"more than {max_pages} pages: stopping")


def odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
