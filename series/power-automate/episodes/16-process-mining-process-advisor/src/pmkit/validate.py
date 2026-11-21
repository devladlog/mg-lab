"""`check` flags what makes an event log a poor input for process mining; `clean` repairs what can be repaired safely.

Rules and where they come from:
  PM001 mandatory columns           Learn: Case ID, Activity and Start timestamp are mandatory attributes
  PM002 empty mandatory values      Learn: the case ID "must be present for all activities in the log"
  PM003 timestamps not ISO 8601     Learn (Azure Data Lake / OneLake pages): "must follow the ISO 8601 standard format"
  PM004 end before start            ours: an activity can't end before it starts
  PM005 spelling variants           ours: one activity written two ways becomes two nodes on the map (Learn's Transform
                                    page: rename activities with Replace values)
  PM006 exact duplicate rows        ours: every copy is another event
  PM007 cases with one event        ours: nothing to mine (no transition)
  PM008 ids inside activity names   Learn (object-centric log page): keep high-cardinality details out of Activity
  PM009 several UTC offsets         Learn (same page): "Single time zone or UTC"
  PM010 file bigger than 100 MB     Learn: the trial offers limited process mining capacity of 100 MB per process
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .eventlog import COLUMNS, Event, fmt, parse_iso, read_rows

REQUIRED = ["CaseId", "ActivityName", "StartTimestamp"]
TRIAL_CAPACITY_MB = 100
_DAYFIRST = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")


@dataclass
class Finding:
    level: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.message}"


def parse_any(text: str, day_first: bool = True) -> datetime:
    """ISO 8601, or dd/MM/yyyy HH:mm[:ss] (month first with day_first=False). Raises ValueError."""
    m = _DAYFIRST.match(text.strip())
    if m:
        a, b, y, hh, mm, ss = m.groups()
        day, month = (int(a), int(b)) if day_first else (int(b), int(a))
        return datetime(int(y), month, day, int(hh), int(mm), int(ss or 0), tzinfo=timezone.utc)
    return parse_iso(text)


def _is_iso(text: str) -> bool:
    try:
        parse_iso(text)
        return True
    except ValueError:
        return False


def check(path, max_mb: float = TRIAL_CAPACITY_MB) -> list[Finding]:
    out: list[Finding] = []
    header, rows = read_rows(path)
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        return [Finding("error", "PM001", f"missing mandatory column(s) {missing}: map Case ID, Activity name and Start timestamp")]
    size_mb = Path(path).stat().st_size / 1_000_000
    if size_mb > max_mb:
        out.append(Finding("error", "PM010", f"file is {size_mb:.1f} MB; the trial allows {max_mb:g} MB of process data per process"))
    empty = Counter(c for r in rows for c in REQUIRED if not (r.get(c) or "").strip())
    for c, n in empty.items():
        out.append(Finding("error", "PM002", f"{n} row(s) have an empty {c}"))
    bad_ts = [i for i, r in enumerate(rows, start=2) for c in ("StartTimestamp", "EndTimestamp")
              if (r.get(c) or "").strip() and not _is_iso(r[c])]
    if bad_ts:
        out.append(Finding("error", "PM003", f"{len(bad_ts)} timestamp(s) aren't ISO 8601 (YYYY-MM-DD HH:MM:SS), first at line {bad_ts[0]}"))
    offsets = {m.group(0) for r in rows for c in ("StartTimestamp", "EndTimestamp")
               if (m := re.search(r"(?:Z|[+-]\d{2}:\d{2})$", r.get(c) or ""))}
    if len(offsets) > 0:
        out.append(Finding("warning", "PM009", f"timestamps carry UTC offsets {sorted(offsets)}: use one time zone, or UTC"))
    swapped = 0
    for r in rows:
        try:
            if (r.get("EndTimestamp") or "").strip() and parse_iso(r["EndTimestamp"]) < parse_iso(r["StartTimestamp"]):
                swapped += 1
        except ValueError:
            pass
    if swapped:
        out.append(Finding("warning", "PM004", f"{swapped} row(s) end before they start"))
    names: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        a = (r.get("ActivityName") or "")
        if a.strip():
            names[re.sub(r"\s+", " ", a.strip()).lower()][a] += 1
    for key, spellings in names.items():
        if len(spellings) > 1:
            out.append(Finding("warning", "PM005", f"activity {key!r} is spelled {len(spellings)} ways: "
                                                   f"{sorted(spellings, key=repr)}"))
    dup = sum(n - 1 for n in Counter(tuple(sorted(r.items())) for r in rows).values() if n > 1)
    if dup:
        out.append(Finding("warning", "PM006", f"{dup} exact duplicate row(s)"))
    per_case = Counter((r.get("CaseId") or "").strip() for r in rows if (r.get("CaseId") or "").strip())
    single = [c for c, n in per_case.items() if n == 1]
    if single:
        out.append(Finding("warning", "PM007", f"{len(single)} case(s) have a single event, e.g. {single[0]}"))
    ids = sorted({r["ActivityName"].strip() for r in rows if re.search(r"\d{4,}", r.get("ActivityName") or "")})
    if ids:
        out.append(Finding("warning", "PM008", f"activity names with ids or long numbers (keep them as attributes): {ids[:3]}"))
    return out


def clean(path, day_first: bool = True) -> tuple[list[Event], dict[str, int]]:
    """Repair what is safe: trim, one spelling per activity, ISO timestamps in UTC, swapped start/end, duplicates.
    Rows without a case id, activity or start can't be repaired and are dropped (and counted)."""
    _, rows = read_rows(path)
    report: Counter = Counter()
    spelled: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        a = re.sub(r"\s+", " ", (r.get("ActivityName") or "").strip())
        if a:
            spelled[a.lower()][a] += 1
    canonical = {k: max(v.items(), key=lambda kv: (kv[1], kv[0] == kv[0].title(), kv[0]))[0] for k, v in spelled.items()}
    seen, out = set(), []
    for r in rows:
        case, act = (r.get("CaseId") or "").strip(), re.sub(r"\s+", " ", (r.get("ActivityName") or "").strip())
        if not case or not act or not (r.get("StartTimestamp") or "").strip():
            report["dropped_incomplete_rows"] += 1
            continue
        if act != canonical[act.lower()]:
            report["renamed_activities"] += 1
        act = canonical[act.lower()]
        try:
            start = parse_any(r["StartTimestamp"], day_first)
            end = parse_any(r["EndTimestamp"], day_first) if (r.get("EndTimestamp") or "").strip() else None
        except ValueError:
            report["dropped_unreadable_timestamps"] += 1
            continue
        if not _is_iso(r["StartTimestamp"]) or (end and not _is_iso(r["EndTimestamp"])):
            report["converted_timestamps"] += 1
        elif re.search(r"(?:Z|[+-]\d{2}:\d{2})$", r["StartTimestamp"].strip()):
            report["converted_timestamps"] += 1
        if end and end < start:
            start, end = end, start
            report["swapped_start_end"] += 1
        ev = Event(case, act, start, end, (r.get("Resource") or "").strip(),
                   float(r["Amount"]) if (r.get("Amount") or "").strip() else None, (r.get("Category") or "").strip())
        key = tuple(ev.row())
        if key in seen:
            report["dropped_duplicates"] += 1
            continue
        seen.add(key)
        out.append(ev)
    out.sort(key=lambda e: (e.case_id, e.start))
    return out, dict(report)
