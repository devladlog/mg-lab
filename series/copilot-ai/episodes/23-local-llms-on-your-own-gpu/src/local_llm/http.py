"""Tiny JSON-over-HTTP helper (urllib) plus a guard that refuses non-local endpoints."""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class LlmHttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url}: {body[:300]}")
        self.status, self.body, self.url = status, body, url


def is_local_url(url: str) -> bool:
    """True for loopback, private-range and link-local hosts, and for 'localhost'. DNS names are not resolved."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def assert_local(url: str) -> None:
    if not is_local_url(url):
        raise ValueError(f"refusing to send data to a non-local endpoint: {url} (use --allow-remote to override)")


def request_json(method: str, url: str, payload: Any | None = None, headers: dict | None = None,
                 timeout: float = 600.0) -> Any:
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {url}")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise LlmHttpError(e.code, e.read().decode("utf-8", "replace"), url) from None
    except urllib.error.URLError as e:
        raise ConnectionError(f"cannot reach {url}: {e.reason}") from None
    return json.loads(raw) if raw.strip() else {}
