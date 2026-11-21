"""JSON over HTTP (urllib) with the key kept in headers, never in URLs or error messages."""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


def is_local_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def post_json(url: str, payload: Any, headers: dict, timeout: float = 120.0) -> Any:
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {url}")
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace")) from None
    except urllib.error.URLError as e:
        raise ConnectionError(f"cannot reach {urllib.parse.urlparse(url).netloc}: {e.reason}") from None
