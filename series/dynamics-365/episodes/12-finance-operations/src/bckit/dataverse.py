"""Minimal Dataverse Web API reader (same request rules as episodes 1-11: Bearer token, 429 + Retry-After, nextLink)."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, Optional

import requests

API_VERSION = "v9.2"


class DataverseError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message = status, message


class DataverseApi:
    def __init__(self, env_url: str, token: Callable[[], str], *, session: Optional[requests.Session] = None,
                 max_retries: int = 5, sleep: Callable[[float], None] = time.sleep):
        self.api = f"{env_url.rstrip('/')}/api/data/{API_VERSION}"
        self._token = token
        self.session = session or requests.Session()
        self.max_retries, self._sleep = max_retries, sleep

    def get_all(self, path: str, page_size: int = 500) -> Iterator[Dict[str, Any]]:
        url: Optional[str] = path if path.startswith("http") else f"{self.api}/{path.lstrip('/')}"
        while url:
            for attempt in range(self.max_retries + 1):
                r = self.session.request("GET", url, headers={
                    "Authorization": f"Bearer {self._token()}", "Accept": "application/json",
                    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Prefer": f"odata.maxpagesize={page_size}"})
                if r.status_code != 429 or attempt == self.max_retries:
                    break
                self._sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
            if r.status_code >= 400:
                try:
                    msg = r.json().get("error", {}).get("message", r.text)
                except ValueError:
                    msg = r.text[:300]
                raise DataverseError(r.status_code, msg)
            page = r.json()
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")
