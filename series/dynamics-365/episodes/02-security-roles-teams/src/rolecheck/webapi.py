"""Minimal read-only Dataverse Web API client: GET with paging and 429 handling. Nothing here writes."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, Optional

import requests


class WebApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class WebApi:
    def __init__(self, env_url: str, token: Callable[[], str], *, session: Optional[requests.Session] = None,
                 max_retries: int = 5, sleep: Callable[[float], None] = time.sleep):
        self.api = env_url.rstrip("/") + "/api/data/v9.2"
        self._token, self.session, self.max_retries, self._sleep = token, session or requests.Session(), max_retries, sleep

    def get(self, path: str, *, annotations: bool = False) -> Dict[str, Any]:
        url = path if path.startswith("http") else f"{self.api}/{path}"
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json",
                   "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                   "Prefer": "odata.maxpagesize=500" + (', odata.include-annotations="*"' if annotations else "")}
        for attempt in range(self.max_retries + 1):
            r = self.session.get(url, headers=headers)
            if r.status_code != 429 or attempt == self.max_retries:
                break
            self._sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise WebApiError(r.status_code, msg)
        return r.json()

    def get_all(self, path: str, *, annotations: bool = False) -> Iterator[Dict[str, Any]]:
        url: Optional[str] = path
        while url:
            page = self.get(url, annotations=annotations)
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")
