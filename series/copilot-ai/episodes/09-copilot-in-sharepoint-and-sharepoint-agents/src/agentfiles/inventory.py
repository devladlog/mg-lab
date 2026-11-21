"""Read the search export of .agent files (written by scripts/Get-AgentFileInventory.ps1) and summarise it.

Learn (Upgrade agents in SharePoint and OneDrive) tells admins to start by inventorying the .agent files and to note each
agent's owner, audience, purpose, knowledge sources and access points. Search gives the first part of that: where the
files are, who created them and how much they are viewed. The rest has to come from people (see plan.py).
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# Columns the collector writes. The reader is case-insensitive and ignores extra columns.
COLUMNS = ["Title", "Path", "Author", "Created", "LastModifiedTime", "SPSiteUrl", "SiteTitle",
           "ViewsLifeTime", "ViewsRecent", "ViewsLifeTimeUniqueUsers"]


@dataclass(frozen=True)
class AgentFile:
    title: str
    path: str
    owner: str
    created: date | None
    modified: date | None
    site_url: str
    site_title: str
    views_lifetime: int
    views_recent: int
    unique_viewers: int

    @property
    def key(self) -> str:
        return normalize_path(self.path)


def normalize_path(path: str) -> str:
    """Compare paths without case, trailing slashes or URL-encoded spaces."""
    return path.strip().replace("%20", " ").rstrip("/").lower()


def _int(value) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _date(value) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def read_inventory(path: Path) -> tuple[list[AgentFile], int]:
    """Return (agent files, number of rows skipped because they were not .agent files)."""
    files: list[AgentFile] = []
    skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            p = row.get("path", "")
            if not p.lower().split("?")[0].endswith(".agent"):
                skipped += 1
                continue
            files.append(AgentFile(
                title=row.get("title", "") or p.rsplit("/", 1)[-1],
                path=p,
                owner=row.get("author", ""),
                created=_date(row.get("created")),
                modified=_date(row.get("lastmodifiedtime")),
                site_url=row.get("spsiteurl", ""),
                site_title=row.get("sitetitle", ""),
                views_lifetime=_int(row.get("viewslifetime")),
                views_recent=_int(row.get("viewsrecent")),
                unique_viewers=_int(row.get("viewslifetimeuniqueusers")),
            ))
    return files, skipped


def summarize(files: list[AgentFile], today: date, stale_days: int = 90) -> dict:
    by_site = Counter(f.site_title or f.site_url or "(unknown site)" for f in files)
    never = [f for f in files if f.views_lifetime == 0]
    stale = [f for f in files if f.modified and (today - f.modified).days > stale_days]
    return {
        "agent_files": len(files),
        "sites": len(by_site),
        "top_sites": by_site.most_common(5),
        "never_viewed": len(never),
        "not_modified_for_days": {"days": stale_days, "count": len(stale)},
        "no_owner": sum(1 for f in files if not f.owner),
    }
