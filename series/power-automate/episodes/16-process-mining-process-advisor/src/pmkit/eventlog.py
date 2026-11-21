"""The event log as the process mining capability wants it: one row per activity.

Learn (Prepare processes and data): Case ID, Activity name and Start timestamp are mandatory; End timestamp makes it an
*activity log*; Resource, event level / case level attributes and financial values are optional. Column names are ours:
the mapping screen lets you pick the attribute type for each column.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ["CaseId", "ActivityName", "StartTimestamp", "EndTimestamp", "Resource", "Amount", "Category"]
# What each column is mapped to on the "Map your data" screen (Learn attribute types)
MAPPING = {"CaseId": "Case ID", "ActivityName": "Activity name", "StartTimestamp": "Start timestamp",
           "EndTimestamp": "End timestamp", "Resource": "Resource", "Amount": "Financial per case (first event)",
           "Category": "Case level attribute (first event)"}
TS_FORMAT = "%Y-%m-%d %H:%M:%S"  # ISO 8601 with a space, as in Learn's example YYYY-MM-DD HH:MM:SS.sss


@dataclass
class Event:
    case_id: str
    activity: str
    start: datetime
    end: datetime | None = None
    resource: str = ""
    amount: float | None = None
    category: str = ""

    def row(self) -> list[str]:
        return [self.case_id, self.activity, fmt(self.start), fmt(self.end) if self.end else "", self.resource,
                f"{self.amount:.2f}" if self.amount is not None else "", self.category]


def fmt(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime(TS_FORMAT)


def parse_iso(text: str) -> datetime:
    """ISO 8601, 'T' or space, optional fraction and offset; naive values are taken as UTC. Raises ValueError."""
    t = text.strip().replace(" ", "T", 1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    d = datetime.fromisoformat(t)
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def write_csv(path, events) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:  # UTF-8, comma, no compression: Learn's CSV requirements
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(COLUMNS)
        for e in events:
            w.writerow(e.row())


def read_rows(path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def read_csv(path) -> list[Event]:
    """Strict reader for a clean log: raises ValueError on the first row `check` would flag."""
    _, rows = read_rows(path)
    out = []
    for n, r in enumerate(rows, start=2):
        try:
            out.append(Event(r["CaseId"].strip(), r["ActivityName"].strip(), parse_iso(r["StartTimestamp"]),
                             parse_iso(r["EndTimestamp"]) if r.get("EndTimestamp", "").strip() else None,
                             r.get("Resource", "").strip(), float(r["Amount"]) if r.get("Amount", "").strip() else None,
                             r.get("Category", "").strip()))
        except (KeyError, ValueError) as e:
            raise ValueError(f"{path}:{n}: {e}") from e
    return out
