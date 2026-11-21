"""Small Dataverse Web API client (same as episodes 3-5): GET/POST/PATCH/DELETE, 429 + Retry-After, update-only PATCH.
Environment variable DEFINITIONS are solution components (sent with MSCRM.SolutionUniqueName); their VALUES are
created with in_solution=False on purpose (Learn: provide values per environment, don't ship them in the solution).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, Mapping, Optional

import requests

API_VERSION = "v9.2"


class DataverseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"HTTP {status} {code}: {message}".replace("  ", " "))
        self.status, self.code, self.message = status, code, message


class WebApi:
    def __init__(self, env_url: str, token: Callable[[], str], *, solution: Optional[str] = None,
                 session: Optional[requests.Session] = None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep):
        self.api = f"{env_url.rstrip('/')}/api/data/{API_VERSION}"
        self._token, self.solution = token, solution
        self.session = session or requests.Session()
        self.max_retries, self._sleep = max_retries, sleep

    def _headers(self, extra: Optional[Mapping[str, str]], in_solution: bool) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json",
             "OData-MaxVersion": "4.0", "OData-Version": "4.0"}
        if in_solution and self.solution:
            h["MSCRM.SolutionUniqueName"] = self.solution
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, path: str, *, json: Any = None, headers: Optional[Mapping[str, str]] = None,
                in_solution: bool = False) -> requests.Response:
        url = path if path.startswith("http") else f"{self.api}/{path.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            r = self.session.request(method, url, json=json, headers=self._headers(headers, in_solution))
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

    def get(self, path: str) -> Dict[str, Any]:
        return self.request("GET", path).json()

    def get_all(self, path: str) -> Iterator[Dict[str, Any]]:
        url: Optional[str] = path
        while url:
            page = self.request("GET", url, headers={"Prefer": "odata.maxpagesize=500"}).json()
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")

    def exists(self, path: str) -> bool:
        try:
            self.request("GET", path)
            return True
        except DataverseError as e:
            if e.status == 404:
                return False
            raise

    def create(self, entity_set: str, body: Dict[str, Any], *, in_solution: bool = True) -> str:
        """POST; returns the new id parsed from OData-EntityId."""
        r = self.request("POST", entity_set, json=body, in_solution=in_solution)
        return entity_id(r.headers.get("OData-EntityId", ""))

    def update(self, path: str, body: Dict[str, Any], *, in_solution: bool = True) -> None:
        # If-Match: * makes PATCH update-only: it never creates a record by accident.
        self.request("PATCH", path, json=body, headers={"If-Match": "*"}, in_solution=in_solution)

    def delete(self, path: str) -> None:
        self.request("DELETE", path)

    def action(self, name: str, body: Dict[str, Any]) -> requests.Response:
        return self.request("POST", name, json=body)


def entity_id(odata_entity_id: str) -> str:
    """'.../webresourceset(1f...)' -> '1f...'; '' when the header is missing."""
    if "(" not in odata_entity_id:
        return ""
    return odata_entity_id.rsplit("(", 1)[1].rstrip(")")


def odata_string(value: str) -> str:
    """A string literal for $filter: single quotes doubled."""
    return "'" + value.replace("'", "''") + "'"
