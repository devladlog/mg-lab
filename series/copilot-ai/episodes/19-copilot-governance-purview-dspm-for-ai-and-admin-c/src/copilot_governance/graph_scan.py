"""Read-only Microsoft Graph scan of sharing links on SharePoint document libraries (top level of each library).

Needs a delegated or application access token for https://graph.microsoft.com that you obtain yourself and pass in the
environment variable GRAPH_TOKEN (never written to disk, never printed). Learn: listing permissions on a driveItem needs
Files.Read.All or Sites.Read.All (least privileged for a work or school account: Files.Read, which only returns what
applies to the caller); sharing-permission properties with secrets are only returned to callers who can create them.
Honours 429/503 Retry-After. Item and site counts are capped so a run stays small.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


class GraphClient:
    def __init__(self, token: str, base: str = GRAPH, sleep: Callable[[float], None] = time.sleep, max_retries: int = 4):
        self.token, self.base, self.sleep, self.max_retries = token, base.rstrip("/"), sleep, max_retries
        self.requests = 0

    def get(self, url: str) -> dict:
        if url.startswith("/"):
            url = self.base + url
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
            self.requests += 1
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (https or loopback in tests)
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < self.max_retries:
                    self.sleep(float(e.headers.get("Retry-After", "1") or 1))
                    continue
                body = e.read().decode("utf-8", "replace")[:300]
                raise GraphError(f"GET {urllib.parse.urlsplit(url).path} -> HTTP {e.code}: {body}") from e
        raise GraphError("retries exhausted")

    def paged(self, url: str, limit: int):
        n = 0
        while url and n < limit:
            page = self.get(url)
            for v in page.get("value", []):
                yield v
                n += 1
                if n >= limit:
                    return
            url = page.get("@odata.nextLink")


def scan(client: GraphClient, query: str = "*", max_sites: int = 10, max_items: int = 200) -> dict:
    result = {"query": query, "sites": []}
    q = urllib.parse.quote(query)
    for site in client.paged(f"/sites?search={q}&$top=50", max_sites):
        entry = {"id": site.get("id"), "name": site.get("displayName") or site.get("name"), "webUrl": site.get("webUrl"), "items": []}
        budget = max_items
        for drive in client.paged(f"/sites/{site['id']}/drives", 20):
            if budget <= 0:
                break
            for item in client.paged(f"/drives/{drive['id']}/root/children?$top=200", budget):
                perms = list(client.paged(f"/drives/{drive['id']}/items/{item['id']}/permissions", 500))
                entry["items"].append({"name": item.get("name"), "path": f"{drive.get('name', 'drive')}/{item.get('name')}",
                                       "isFolder": "folder" in item, "permissions": perms})
                budget -= 1
        result["sites"].append(entry)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="graph_scan", description=__doc__)
    p.add_argument("--query", default="*", help="site search text (GET /sites?search=)")
    p.add_argument("--max-sites", type=int, default=10)
    p.add_argument("--max-items", type=int, default=200, help="items per site")
    p.add_argument("--out", required=True)
    p.add_argument("--base", default=GRAPH, help="override only for tests")
    args = p.parse_args(argv)
    token = os.environ.get("GRAPH_TOKEN")
    if not token:
        print("Set GRAPH_TOKEN to a Microsoft Graph access token (not stored or printed by this tool).", file=sys.stderr)
        return 2
    client = GraphClient(token, base=args.base)
    try:
        data = scan(client, args.query, args.max_sites, args.max_items)
    except GraphError as e:
        print(f"Graph error: {e}", file=sys.stderr)
        return 4
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(f"{len(data['sites'])} site(s), {sum(len(s['items']) for s in data['sites'])} item(s), {client.requests} request(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
