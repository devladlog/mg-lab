"""Small Dataverse Web API client (same as episodes 3-8): GET/POST/PATCH, 429 + Retry-After, update-only PATCH.
Adds `get_all(..., annotations=True)` to ask for formatted values (choice labels, lookup names) with the OData
annotation Learn documents: Prefer: odata.include-annotations="OData.Community.Display.V1.FormattedValue".
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, Mapping, Optional

import requests

API_VERSION = "v9.2"
FORMATTED = 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'


class DataverseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"HTTP {status} {code}: {message}".replace("  ", " "))
        self.status, self.code, self.message = status, code, message


class WebApi:
    def __init__(self, env_url: str, token: Callable[[], str], *, session: Optional[requests.Session] = None,
                 max_retries: int = 5, sleep: Callable[[float], None] = time.sleep):
        self.api = f"{env_url.rstrip('/')}/api/data/{API_VERSION}"
        self._token = token
        self.session = session or requests.Session()
        self.max_retries, self._sleep = max_retries, sleep

    def _headers(self, extra: Optional[Mapping[str, str]]) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json",
             "OData-MaxVersion": "4.0", "OData-Version": "4.0"}
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, path: str, *, json: Any = None,
                headers: Optional[Mapping[str, str]] = None) -> requests.Response:
        url = path if path.startswith("http") else f"{self.api}/{path.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            r = self.session.request(method, url, json=json, headers=self._headers(headers))
            if r.status_code != 429 or attempt == self.max_retries:
                break
            self._sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                raise DataverseError(r.status_code, err.get("code", ""), err.get("message", r.text))
            except ValueError:
                raise DataverseError(r.status_code, "", r.text[:300]) from None
        return r

    def get(self, path: str, *, annotations: bool = False) -> Dict[str, Any]:
        h = {"Prefer": FORMATTED} if annotations else None
        return self.request("GET", path, headers=h).json()

    def get_all(self, path: str, *, annotations: bool = False, page_size: int = 500) -> Iterator[Dict[str, Any]]:
        prefer = f"odata.maxpagesize={page_size}" + (f",{FORMATTED}" if annotations else "")
        url: Optional[str] = path
        while url:
            page = self.request("GET", url, headers={"Prefer": prefer}).json()
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")

    def post(self, path: str, body: Dict[str, Any]) -> requests.Response:
        return self.request("POST", path, json=body)

    def update(self, path: str, body: Dict[str, Any]) -> None:
        # If-Match: * makes PATCH update-only: it never creates a record by accident.
        self.request("PATCH", path, json=body, headers={"If-Match": "*"})


def odata_string(value: str) -> str:
    """A string literal for $filter: single quotes doubled."""
    return "'" + value.replace("'", "''") + "'"
