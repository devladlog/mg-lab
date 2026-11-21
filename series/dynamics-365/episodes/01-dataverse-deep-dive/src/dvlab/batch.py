"""OData $batch: build a multipart/mixed body (optionally one change set = one transaction) and parse the reply.

Learn rules we follow here:
- a batch holds at most 1,000 requests and can't contain another batch;
- GET requests are not allowed inside a change set;
- line endings must be CRLF;
- headers on the outer $batch request don't apply to the items, so each item carries its own.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_BATCH_REQUESTS = 1000
CRLF = "\r\n"


@dataclass
class BatchItem:
    method: str
    url: str                       # relative to the api root, e.g. "mgl_projectrequests(mgl_requestcode='PR-1')"
    body: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class BatchResult:
    status: int
    headers: Dict[str, str]
    body: Any


def build_batch(items: List[BatchItem], api_root: str, *, changeset: bool = True,
                boundary: Optional[str] = None) -> tuple[str, str]:
    """Return (content_type, body). With changeset=True all items succeed or fail together."""
    if not items:
        raise ValueError("A batch needs at least one request.")
    if len(items) > MAX_BATCH_REQUESTS:
        raise ValueError(f"A batch can hold at most {MAX_BATCH_REQUESTS} requests, got {len(items)}.")
    if changeset and any(i.method.upper() == "GET" for i in items):
        raise ValueError("GET requests aren't allowed inside a change set.")

    batch_id = boundary or f"batch_{uuid.uuid4().hex}"
    lines: List[str] = []

    def item_lines(item: BatchItem, content_id: Optional[int]) -> List[str]:
        out = ["Content-Type: application/http", "Content-Transfer-Encoding: binary"]
        if content_id is not None:
            out.append(f"Content-ID: {content_id}")
        out += ["", f"{item.method.upper()} {api_root.rstrip('/')}/{item.url} HTTP/1.1"]
        hdrs = {"Accept": "application/json", **item.headers}
        if item.body is not None:
            hdrs["Content-Type"] = "application/json; type=entry"
        out += [f"{k}: {v}" for k, v in hdrs.items()]
        out.append("")
        if item.body is not None:
            out.append(json.dumps(item.body, separators=(",", ":")))
        return out

    if changeset:
        cs_id = f"changeset_{uuid.uuid4().hex}"
        lines += [f"--{batch_id}", f'Content-Type: multipart/mixed; boundary="{cs_id}"', ""]
        for n, item in enumerate(items, start=1):
            lines.append(f"--{cs_id}")
            lines += item_lines(item, n)
        lines.append(f"--{cs_id}--")
    else:
        for item in items:
            lines.append(f"--{batch_id}")
            lines += item_lines(item, None)
    lines.append(f"--{batch_id}--")
    lines.append("")
    return f'multipart/mixed; boundary="{batch_id}"', CRLF.join(lines)


_STATUS = re.compile(r"^HTTP/1\.1 (\d{3})")


def parse_batch_response(content_type: str, text: str) -> List[BatchResult]:
    """Split a batch response into one BatchResult per inner response (change sets are flattened)."""
    m = re.search(r'boundary="?([^";]+)"?', content_type)
    if not m:
        raise ValueError(f"No boundary in Content-Type {content_type!r}")
    return _parse_part(text.replace("\r\n", "\n"), m.group(1))


def _parse_part(text: str, boundary: str) -> List[BatchResult]:
    results: List[BatchResult] = []
    for chunk in text.split(f"--{boundary}"):
        chunk = chunk.strip("\n")
        if not chunk or chunk.startswith("--"):
            continue
        head, _, rest = chunk.partition("\n\n")
        nested = re.search(r'Content-Type: multipart/mixed; boundary="?([^";\n]+)"?', head, re.I)
        if nested:
            results += _parse_part(rest, nested.group(1))
            continue
        status_line, _, rest = rest.partition("\n")
        sm = _STATUS.match(status_line.strip())
        if not sm:
            continue
        lines = rest.split("\n")
        headers = {}
        while lines and lines[0].strip():          # headers end at the first empty line (there may be none)
            k, _, v = lines.pop(0).partition(":")
            headers[k.strip()] = v.strip()
        body = "\n".join(lines).strip()
        try:
            parsed: Any = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        results.append(BatchResult(int(sm.group(1)), headers, parsed))
    return results
