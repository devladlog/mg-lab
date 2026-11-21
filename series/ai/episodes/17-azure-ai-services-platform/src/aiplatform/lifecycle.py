"""Find the retiring services in your own code, with the date and the days left.

The register is data (`data/lifecycle.json`, each date copied from a Learn page). The scanner is a line-by-line regex match
over source and infrastructure files: it finds *use*, it cannot tell you whether the path is hot. A hit is a question to ask."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[2] / "data" / "lifecycle.json"
EXTENSIONS = {".py", ".cs", ".ts", ".js", ".java", ".kt", ".bicep", ".json", ".yaml", ".yml", ".ps1"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "bin", "obj", "__pycache__", "tests", "test", "screens", "build", "out"}
SKIP_FILES = {"lifecycle.json", "package-lock.json", "script.yaml"}
MAX_BYTES = 1_000_000


@dataclass
class Entry:
    id: str
    service: str
    retires: date
    replacement: str
    url: str
    patterns: list[re.Pattern]
    plan_by: date | None = None


@dataclass
class Hit:
    entry: Entry
    path: str
    line: int
    text: str


def load_register(path: Path | None = None) -> list[Entry]:
    raw = json.loads((path or REGISTER).read_text(encoding="utf-8"))
    out = []
    for e in raw["entries"]:
        out.append(Entry(e["id"], e["service"], date.fromisoformat(e["retires"]), e["replacement"], e["url"],
                         [re.compile(p, re.I) for p in e["patterns"]], date.fromisoformat(e["plan_by"]) if e.get("plan_by") else None))
    return out


def scan(root: Path, entries: list[Entry] | None = None, include_tests: bool = False) -> list[Hit]:
    entries = entries or load_register()
    skip = SKIP_DIRS - ({"tests", "test"} if include_tests else set())
    hits: list[Hit] = []
    root = Path(root)
    files = [root] if root.is_file() else sorted(root.rglob("*"))
    for f in files:
        if not f.is_file() or f.suffix.lower() not in EXTENSIONS or f.name in SKIP_FILES:
            continue
        if any(part in skip for part in f.relative_to(root if root.is_dir() else root.parent).parts[:-1]):
            continue
        if f.stat().st_size > MAX_BYTES:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(f.relative_to(root)) if root.is_dir() else f.name
        for n, line in enumerate(lines, 1):
            for e in entries:
                if any(p.search(line) for p in e.patterns):
                    hits.append(Hit(e, rel, n, line.strip()[:110]))
    return hits


def status(e: Entry, today: date, urgent_days: int = 180, plan_days: int = 730) -> tuple[str, int]:
    left = (e.retires - today).days
    if left <= 0:
        return "RETIRED", left
    if left <= urgent_days:
        return "URGENT", left
    if left <= plan_days:
        return "PLAN", left
    return "TRACK", left


def summarise(hits: list[Hit], today: date) -> list[dict]:
    """One row per register entry that has hits, soonest retirement first."""
    by: dict[str, list[Hit]] = {}
    for h in hits:
        by.setdefault(h.entry.id, []).append(h)
    rows = []
    for hs in by.values():
        e = hs[0].entry
        st, left = status(e, today)
        rows.append({"entry": e, "status": st, "days": left, "hits": hs, "files": sorted({h.path for h in hs})})
    return sorted(rows, key=lambda r: r["entry"].retires)


def render(rows: list[dict], today: date, show_lines: bool = True) -> str:
    if not rows:
        return f"No retiring service found in the scanned files (checked {today.isoformat()})."
    out = [f"Lifecycle check, as of {today.isoformat()}"]
    for r in rows:
        e: Entry = r["entry"]
        when = f"retired {-r['days']} days ago" if r["days"] <= 0 else f"{r['days']} days left"
        out.append(f"\n{r['status']:<8} {e.service}\n         retires {e.retires.isoformat()} ({when}); {len(r['hits'])} hit(s) in {len(r['files'])} file(s)")
        if e.plan_by:
            out.append(f"         Learn asks for a transition plan by {e.plan_by.isoformat()}" + (" (already passed)" if e.plan_by < today else ""))
        out.append(f"         move to: {e.replacement}\n         source: {e.url}")
        if show_lines:
            for h in r["hits"][:6]:
                out.append(f"           {h.path}:{h.line}  {h.text}")
            if len(r["hits"]) > 6:
                out.append(f"           ... {len(r['hits']) - 6} more")
    return "\n".join(out)


def exit_code(rows: list[dict], fail_within_days: int = 0) -> int:
    """1 when something already retired is still used, or retires within the window (default: only the retired)."""
    return 1 if any(r["days"] <= fail_within_days for r in rows) else 0
