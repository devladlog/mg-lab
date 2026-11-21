"""Read files from SharePoint document libraries with Microsoft Graph (plain REST over httpx).

App-only with Sites.Selected: the ingestion identity can read only the sites it was explicitly granted.
  GET /sites/{hostname}:/{site-path}                 -> site id
  GET /sites/{site-id}/drives                        -> library (drive) by name
  GET /drives/{drive-id}/items/{item-id}/children    -> files and folders, paged with @odata.nextLink
  GET /drives/{drive-id}/items/{item-id}/content     -> 302 to a pre-authenticated download URL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

import httpx2 as httpx  # the HTTP client the openai SDK already ships with

GRAPH = "https://graph.microsoft.com/v1.0"
TEXT_EXTENSIONS = (".md", ".txt")


@dataclass(frozen=True)
class DriveFile:
    drive_id: str
    item_id: str
    name: str
    web_url: str
    modified: str
    path: str


class GraphSource:
    def __init__(self, token: Callable[[], str], http: httpx.Client | None = None):
        self._token = token
        self._http = http or httpx.Client(timeout=60)

    def _get(self, url: str, **params) -> dict:
        r = self._http.get(url if url.startswith("http") else f"{GRAPH}{url}", params=params or None,
                           headers={"Authorization": f"Bearer {self._token()}"})
        r.raise_for_status()
        return r.json()

    def site_id(self, site: str) -> str:
        return self._get(f"/sites/{site}")["id"]

    def drive_id(self, site_id: str, library: str) -> str:
        drives = self._get(f"/sites/{site_id}/drives")["value"]
        for d in drives:
            if d["name"] == library:
                return d["id"]
        raise LookupError(f"Library '{library}' not found. Found: {', '.join(d['name'] for d in drives)}")

    def iter_files(self, drive_id: str, item_id: str = "root", path: str = "") -> Iterator[DriveFile]:
        url = f"/drives/{drive_id}/items/{item_id}/children"
        params = {"$select": "id,name,webUrl,file,folder,lastModifiedDateTime"}
        while url:
            page = self._get(url, **params)
            for it in page.get("value", []):
                if "folder" in it:
                    yield from self.iter_files(drive_id, it["id"], f"{path}{it['name']}/")
                elif "file" in it:
                    yield DriveFile(drive_id, it["id"], it["name"], it["webUrl"], it["lastModifiedDateTime"],
                                    f"{path}{it['name']}")
            url, params = page.get("@odata.nextLink"), {}   # nextLink already carries the query

    def download(self, f: DriveFile) -> bytes:
        """/content answers 302 to a pre-authenticated URL. Follow it WITHOUT our bearer token."""
        r = self._http.get(f"{GRAPH}/drives/{f.drive_id}/items/{f.item_id}/content",
                           headers={"Authorization": f"Bearer {self._token()}"}, follow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            r = self._http.get(r.headers["Location"], follow_redirects=False)   # no Authorization header
        r.raise_for_status()
        return r.content
