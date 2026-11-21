"""Item-level oversharing summary from the Microsoft Graph permission scan (graph_scan.py output).

Graph `permission` objects carry a `link` (with `type` and, on SharePoint/OneDrive for work or school, a `scope` of
anonymous, organization or users) when the permission is a sharing link. `inheritedFrom` is set when it comes from a parent.
The name keywords are a heuristic, not a classifier: the real sensitivity answer comes from labels and sensitive
information types in Purview.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SENSITIVE_NAME = re.compile(
    r"(?<![a-z])(salar|payroll|passport|iban|contract|nda|confidential|severance|invoice|hr|disciplin|medical|tax)",
    re.I)  # prefix match at a word start: "salary" and "hr-bands" hit, "calendar" (contains "nda") does not


@dataclass
class ItemExposure:
    site: str
    path: str
    anonymous_links: int = 0
    org_links: int = 0
    specific_links: int = 0
    direct_grants: int = 0
    sensitive_name: bool = False

    @property
    def risk(self) -> str:
        if self.anonymous_links:
            return "high" if self.sensitive_name else "medium"
        if self.org_links:
            return "high" if self.sensitive_name else "low"
        return "none"


@dataclass
class SiteExposure:
    site: str
    items_scanned: int = 0
    exposed: list[ItemExposure] = field(default_factory=list)

    def count(self, attr: str) -> int:
        return sum(getattr(i, attr) for i in self.exposed)


def classify_permission(perm: dict) -> str:
    link = perm.get("link")
    if isinstance(link, dict):
        scope = str(link.get("scope", "")).lower()
        # Learn (sharingLink): scope = anonymous | organization | existingAccess | users
        if scope in ("anonymous", "organization", "users", "existingaccess"):
            return {"anonymous": "anonymous", "organization": "org", "users": "specific", "existingaccess": "specific"}[scope]
        return "link-unknown-scope"
    return "direct"


def analyse(scan: dict) -> list[SiteExposure]:
    out: list[SiteExposure] = []
    for site in scan.get("sites", []):
        se = SiteExposure(site=str(site.get("name") or site.get("webUrl") or site.get("id")))
        for item in site.get("items", []):
            se.items_scanned += 1
            ie = ItemExposure(site=se.site, path=str(item.get("path") or item.get("name")),
                              sensitive_name=bool(SENSITIVE_NAME.search(str(item.get("name", "")))))
            for perm in item.get("permissions", []):
                kind = classify_permission(perm)
                if kind == "anonymous":
                    ie.anonymous_links += 1
                elif kind == "org":
                    ie.org_links += 1
                elif kind == "specific":
                    ie.specific_links += 1
                elif kind == "direct" and not perm.get("inheritedFrom"):
                    ie.direct_grants += 1
            if ie.anonymous_links or ie.org_links:
                se.exposed.append(ie)
        out.append(se)
    return out


def load_scan(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def format_sites(sites: list[SiteExposure]) -> str:
    lines = ["Item-level sharing links (Graph scan)", ""]
    for s in sites:
        lines.append(f"{s.site}: {s.items_scanned} item(s) scanned, {len(s.exposed)} with Anyone or organization-wide links "
                     f"({s.count('anonymous_links')} anonymous, {s.count('org_links')} organization)")
        for i in sorted(s.exposed, key=lambda x: ("high", "medium", "low").index(x.risk)):
            lines.append(f"  [{i.risk:6}] {i.path}  anonymous={i.anonymous_links} org={i.org_links}"
                         + ("  (name looks sensitive)" if i.sensitive_name else ""))
    return "\n".join(lines)
