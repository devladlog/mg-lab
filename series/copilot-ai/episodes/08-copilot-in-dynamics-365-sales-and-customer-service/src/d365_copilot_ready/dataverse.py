"""Tiny read-only Dataverse Web API client (standard library only).

Paging follows the Learn rules: send ``Prefer: odata.maxpagesize``, follow ``@odata.nextLink`` exactly as returned,
never use ``$skip`` and never append query options to a next link.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterator

API_PATH = "/api/data/v9.2/"
_LOCAL = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")


class DataverseError(RuntimeError):
    pass


def mask_org_url(url: str) -> str:
    """Hide the organisation name: https://contoso.crm4.dynamics.com -> https://***.crm4.dynamics.com

    IP addresses and single-label hosts (localhost) are returned unchanged.
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    labels = host.split(".")
    if len(labels) > 2 and not all(x.isdigit() for x in labels):
        labels[0] = "***"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{'.'.join(labels)}{port}"


class DataverseClient:
    def __init__(self, org_url: str, token: str, page_size: int = 500,
                 opener: Callable = urllib.request.urlopen, timeout: float = 60.0):
        org_url = org_url.rstrip("/")
        if not (org_url.startswith("https://") or _LOCAL.match(org_url)):
            raise ValueError("org url must be https (plain http is accepted only for localhost in tests)")
        if not token:
            raise ValueError("an access token is required")
        if not 1 <= page_size <= 5000:
            raise ValueError("page size must be between 1 and 5000 (Learn: larger values are ignored)")
        self.org_url = org_url
        self._token = token
        self.page_size = page_size
        self._opener = opener
        self._timeout = timeout

    def __repr__(self) -> str:  # never show the token
        return f"DataverseClient(org={mask_org_url(self.org_url)!r}, token='***')"

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": f"odata.maxpagesize={self.page_size}",
        })
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                pass
            raise DataverseError(f"HTTP {e.code} for {mask_org_url(url)}...: {detail or e.reason}") from None

    def get_all(self, entity_set: str, select: list[str] | None = None, filter: str | None = None) -> Iterator[dict]:
        query = []
        if select:
            query.append("$select=" + ",".join(select))
        if filter:
            query.append("$filter=" + urllib.parse.quote(filter, safe="=,()'"))
        url = self.org_url + API_PATH + entity_set + ("?" + "&".join(query) if query else "")
        seen = set()
        while url:
            if url in seen:
                raise DataverseError("paging loop: same next link twice")
            seen.add(url)
            page = self._get(url)
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")
