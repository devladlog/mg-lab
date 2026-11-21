"""A small, honest Dataverse Web API client: metadata, upsert by alternate key, paging, $batch, throttling.

Plain `requests` on purpose, so every header is visible. In production you can also use the official
Dataverse SDK for Python (PowerPlatform-Dataverse-Client) or the .NET ServiceClient, which handle 429s for you.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional
from urllib.parse import quote

import requests

from . import schema
from .batch import BatchItem, BatchResult, build_batch, parse_batch_response
from .keys import KeyValue, key_segment

API_VERSION = "v9.2"
MAX_PAGE_SIZE = 5000   # the service ignores odata.maxpagesize above 5,000


class DataverseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class DataverseClient:
    def __init__(self, env_url: str, token: Callable[[], str], *, session: Optional[requests.Session] = None,
                 solution: Optional[str] = None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep):
        self.env_url = env_url.rstrip("/")
        self.api = f"{self.env_url}/api/data/{API_VERSION}"
        self._token = token
        self.session = session or requests.Session()
        self.solution = solution
        self.max_retries = max_retries
        self._sleep = sleep
        self.retries_done = 0   # how many 429s we waited out (shown in the demo)

    # ---------- plumbing ----------
    def _headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, url: str, *, json: Any = None, data: Optional[str] = None,
                headers: Optional[Mapping[str, str]] = None) -> requests.Response:
        """Send one request; on 429 wait for Retry-After seconds (or back off exponentially) and retry."""
        full = url if url.startswith("http") else f"{self.api}/{url.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            resp = self.session.request(method, full, json=json, data=data, headers=self._headers(headers))
            if resp.status_code != 429:
                break
            if attempt == self.max_retries:
                break
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else float(2 ** attempt)
            self.retries_done += 1
            self._sleep(wait)
        if resp.status_code >= 400:
            raise _error(resp)
        return resp

    # ---------- metadata ----------
    def _solution_header(self) -> Dict[str, str]:
        # Tables, columns and keys are solution components: create them inside our solution, not Default.
        return {"MSCRM.SolutionUniqueName": self.solution} if self.solution else {}

    def create_table(self, entity_metadata: Dict[str, Any]) -> str:
        r = self.request("POST", "EntityDefinitions", json=entity_metadata, headers=self._solution_header())
        return r.headers.get("OData-EntityId", "")

    def table_exists(self, logical_name: str) -> bool:
        try:
            self.request("GET", f"EntityDefinitions(LogicalName='{logical_name}')?$select=LogicalName")
            return True
        except DataverseError as e:
            if e.status == 404:
                return False
            raise

    def add_column(self, table: str, attribute: Dict[str, Any]) -> str:
        r = self.request("POST", f"EntityDefinitions(LogicalName='{table}')/Attributes", json=attribute,
                         headers=self._solution_header())
        return r.headers.get("OData-EntityId", "")

    def create_relationship(self, relationship: Dict[str, Any]) -> str:
        r = self.request("POST", "RelationshipDefinitions", json=relationship, headers=self._solution_header())
        return r.headers.get("OData-EntityId", "")

    def create_key(self, table: str, key: Dict[str, Any]) -> str:
        r = self.request("POST", f"EntityDefinitions(LogicalName='{table}')/Keys", json=key,
                         headers=self._solution_header())
        return r.headers.get("OData-EntityId", "")

    def key_status(self, table: str, key_schema: str) -> Optional[str]:
        r = self.request("GET", f"EntityDefinitions(LogicalName='{table}')/Keys"
                                "?$select=SchemaName,KeyAttributes,EntityKeyIndexStatus")
        for k in r.json().get("value", []):
            if k.get("SchemaName", "").lower() == key_schema.lower():
                return k.get("EntityKeyIndexStatus")
        return None

    def wait_for_key(self, table: str, key_schema: str, *, timeout_s: float = 600, poll_s: float = 10,
                     on_poll: Optional[Callable[[str], None]] = None) -> str:
        """Poll until the key's index is Active. Upsert by key before that fails."""
        waited = 0.0
        while True:
            status = self.key_status(table, key_schema) or "Missing"
            if on_poll:
                on_poll(status)
            if status == "Active":
                return status
            if status == "Failed":
                raise DataverseError(0, "KeyIndexFailed",
                                     f"Index for key {key_schema} failed: fix the data, then ReactivateEntityKey.")
            if waited >= timeout_s:
                raise TimeoutError(f"Key {key_schema} still {status} after {timeout_s:.0f}s")
            self._sleep(poll_s)
            waited += poll_s

    def publish(self, tables: List[str]) -> None:
        xml = "<importexportxml><entities>" + "".join(f"<entity>{t}</entity>" for t in tables) + \
              "</entities></importexportxml>"
        self.request("POST", "PublishXml", json={"ParameterXml": xml})

    # ---------- data ----------
    def upsert(self, entity_set: str, key: Mapping[str, KeyValue], data: Dict[str, Any], *,
               mode: str = "upsert", return_id: bool = False) -> Optional[str]:
        """PATCH by alternate key. mode: 'upsert' | 'create-only' (If-None-Match: *) | 'update-only' (If-Match: *).

        Don't put the key columns in the body: on update they're ignored, on create the URL values are used.
        With return_id the response is 201 (created) or 200 (updated): returns 'created' or 'updated'.
        """
        headers: Dict[str, str] = {}
        if mode == "create-only":
            headers["If-None-Match"] = "*"
        elif mode == "update-only":
            headers["If-Match"] = "*"
        elif mode != "upsert":
            raise ValueError(mode)
        body = {k: v for k, v in data.items() if k not in key}
        url = f"{entity_set}{key_segment(key)}"
        if return_id:
            headers["Prefer"] = "return=representation"
            url += f"?$select={schema.TABLE}id" if entity_set == schema.ENTITY_SET else ""
        r = self.request("PATCH", url, json=body, headers=headers)
        if return_id:
            return "created" if r.status_code == 201 else "updated"
        return r.headers.get("OData-EntityId")

    def query(self, entity_set: str, *, select: List[str], filter: Optional[str] = None,
              orderby: Optional[str] = None, page_size: int = 500,
              annotations: bool = True) -> Iterator[List[Dict[str, Any]]]:
        """Yield pages. Follows @odata.nextLink exactly as returned (never edited) with the same page size."""
        if not 0 < page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be 1..{MAX_PAGE_SIZE}")
        params = [f"$select={','.join(select)}"]
        if filter:
            params.append("$filter=" + quote(filter, safe="'(),= "))
        if orderby:
            params.append(f"$orderby={orderby}")
        url: Optional[str] = f"{entity_set}?" + "&".join(params)
        prefer = f"odata.maxpagesize={page_size}"
        if annotations:
            prefer += ', odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
        while url:
            r = self.request("GET", url, headers={"Prefer": prefer})
            payload = r.json()
            yield payload.get("value", [])
            url = payload.get("@odata.nextLink")

    def batch(self, items: List[BatchItem], *, changeset: bool = True,
              continue_on_error: bool = False) -> List[BatchResult]:
        content_type, body = build_batch(items, self.api, changeset=changeset)
        headers = {"Content-Type": content_type}
        if continue_on_error:
            headers["Prefer"] = "odata.continue-on-error"
        r = self.request("POST", "$batch", data=body, headers=headers)
        return parse_batch_response(r.headers.get("Content-Type", ""), r.text)


def _error(resp: requests.Response) -> DataverseError:
    try:
        err = resp.json().get("error", {})
        return DataverseError(resp.status_code, err.get("code", ""), err.get("message", resp.text))
    except ValueError:
        return DataverseError(resp.status_code, "", resp.text[:300])
