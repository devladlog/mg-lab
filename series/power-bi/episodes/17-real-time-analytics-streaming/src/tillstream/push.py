"""The legacy path: a Power BI push (and push/streaming) semantic model fed by the REST API.

Real-time streaming in Power BI is being retired: Learn says creation of streaming models stays enabled until
31 October 2027, after that new push, streaming and PubNub semantic models can no longer be created, and existing ones
keep working. This module exists to show the limits that bite and to feed the lab's comparison, not as a recommendation.

Only the standard library is used. The access token comes from the caller (an environment variable in the CLI); this
module never signs anyone in.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Iterable, Iterator

from events import FIELDS

# Learn, "Push semantic model limitations"
MAX_ROWS_PER_POST = 10_000
MAX_ROWS_PER_HOUR = 1_000_000
MAX_POSTS_PER_MINUTE = 120
MAX_ROWS_FIFO = 200_000
# Learn, "Real-time streaming in Power BI": a streaming tile accepts requests of at most 15 KB
MAX_STREAMING_REQUEST_BYTES = 15 * 1024

TABLE = "TillEvents"
_TYPES = {"EventTime": "DateTime", "Quantity": "Int64", "UnitPrice": "Double", "Amount": "Double"}


def dataset_definition(name: str = "TillEventsLegacy") -> dict:
    """Body of Datasets PostDatasetInGroup: push + streaming ("pushStreaming"), one table, one measure."""
    return {
        "name": name,
        "defaultMode": "PushStreaming",
        "tables": [{
            "name": TABLE,
            "columns": [{"name": c, "dataType": _TYPES.get(c, "string")} for c in FIELDS],
            "measures": [{"name": "Sales Amount", "expression": f"SUM({TABLE}[Amount])"}],
        }],
    }


def chunk_rows(rows: Iterable[dict], max_rows: int = MAX_ROWS_PER_POST, max_bytes: int | None = None) -> Iterator[list[dict]]:
    """Group rows into POST bodies of at most ``max_rows`` rows and, if given, at most ``max_bytes`` bytes of JSON."""
    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    chunk: list[dict] = []
    size = len('{"rows":[]}')
    for row in rows:
        row_size = len(json.dumps(row, separators=(",", ":")).encode("utf-8")) + 1
        if max_bytes is not None and size + row_size > max_bytes and not chunk:
            raise ValueError(f"one row is {row_size} bytes, more than max_bytes={max_bytes}")
        if chunk and (len(chunk) >= max_rows or (max_bytes is not None and size + row_size > max_bytes)):
            yield chunk
            chunk, size = [], len('{"rows":[]}')
        chunk.append(row)
        size += row_size
    if chunk:
        yield chunk


class PushError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Power BI returned HTTP {status}: {body[:300]}")
        self.status = status


class PushClient:
    def __init__(self, token: str, base_url: str = "https://api.powerbi.com", sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = 5):
        parts = token.split(None, 1)
        if parts and parts[0].lower() == "bearer":  # some tools print the whole Authorization header value
            token = parts[1] if len(parts) > 1 else ""
        token = token.strip()
        if not token:
            raise ValueError("an access token is required")
        self._token, self._base, self._sleep, self._retries = token, base_url.rstrip("/"), sleep, max_retries

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        for attempt in range(self._retries + 1):
            req = urllib.request.Request(f"{self._base}{path}", data=data, method=method,
                                         headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https base url, or a local test server)
                    text = resp.read().decode("utf-8")
                    return json.loads(text) if text else {}
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self._retries:  # Learn: 429 with a Retry-After header
                    self._sleep(float(e.headers.get("Retry-After", "1")))
                    continue
                raise PushError(e.code, e.read().decode("utf-8", "replace")) from None
        raise AssertionError("unreachable")

    def create_dataset(self, workspace_id: str, definition: dict, retention: str = "basicFIFO") -> str:
        out = self._request("POST", f"/v1.0/myorg/groups/{workspace_id}/datasets?defaultRetentionPolicy={retention}", definition)
        return out["id"]

    def post_rows(self, workspace_id: str, dataset_id: str, rows: Iterable[dict], table: str = TABLE,
                  max_bytes: int | None = None, max_rows: int = MAX_ROWS_PER_POST) -> int:
        """POST the rows in chunks. Returns the number of requests. Paces itself to the per-minute limit."""
        posts, started = 0, time.monotonic()
        for chunk in chunk_rows(rows, max_rows=max_rows, max_bytes=max_bytes):
            if posts and posts % MAX_POSTS_PER_MINUTE == 0:
                self._sleep(max(0.0, 60 - (time.monotonic() - started)))
                started = time.monotonic()
            self._request("POST", f"/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/tables/{table}/rows", {"rows": chunk})
            posts += 1
        return posts

    def delete_rows(self, workspace_id: str, dataset_id: str, table: str = TABLE) -> None:
        self._request("DELETE", f"/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/tables/{table}/rows")

    def delete_dataset(self, workspace_id: str, dataset_id: str) -> None:
        self._request("DELETE", f"/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}")

    def get(self, path: str) -> dict:
        return self._request("GET", path)
