"""Finance and operations OData client.

What Learn documents (Open Data Protocol (OData), Service endpoints overview, Service protection API limits):
- the endpoint is <environment URL>/data/<public collection name>; the token resource is the environment URL
  without a trailing slash
- by default OData returns only the user's default company; add cross-company=true for every company the user can
  access; filter one company with $filter=dataAreaId eq '<id>' together with cross-company=true
- server-driven paging, maximum page size 10,000: follow @odata.nextLink until it is gone
- throttled requests answer 429 with a Retry-After header (seconds); retried requests get no priority over new ones
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import quote

import requests


class FoError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message = status, message


class FoApi:
    def __init__(self, env_url: str, token: Callable[[], str], *, session: Optional[requests.Session] = None,
                 max_retries: int = 5, sleep: Callable[[float], None] = time.sleep):
        self.base = env_url.rstrip("/") + "/data"
        self._token = token
        self.session = session or requests.Session()
        self.max_retries, self._sleep = max_retries, sleep

    def request(self, url: str) -> Dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            r = self.session.request("GET", url, headers={"Authorization": f"Bearer {self._token()}",
                                                          "Accept": "application/json"})
            if r.status_code != 429 or attempt == self.max_retries:
                break
            self._sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") if isinstance(err.get("message"), str) else err.get("message", {}).get("value")
            except ValueError:
                msg = None
            raise FoError(r.status_code, msg or r.text[:300])
        return r.json()

    def url(self, entity: str, *, select: Optional[List[str]] = None, filter: Optional[str] = None,
            top: Optional[int] = None, cross_company: bool = False) -> str:
        parts = []
        if select:
            parts.append("$select=" + ",".join(select))
        if filter:
            parts.append("$filter=" + quote(filter, safe="=,()'"))
        if top:
            parts.append(f"$top={top}")
        if cross_company:
            parts.append("cross-company=true")
        return f"{self.base}/{entity}" + ("?" + "&".join(parts) if parts else "")

    def get_all(self, url: str) -> Iterator[Dict[str, Any]]:
        nxt: Optional[str] = url
        while nxt:
            page = self.request(nxt)
            yield from page.get("value", [])
            nxt = page.get("@odata.nextLink")


def odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
