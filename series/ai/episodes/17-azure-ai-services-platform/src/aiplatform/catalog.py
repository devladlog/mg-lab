"""Which service for which job, from `data/catalog.json` (every row has its Learn page). Filter with --task."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[2] / "data" / "catalog.json"


def load(path: Path | None = None) -> list[dict]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))["services"]


def find(rows: list[dict], text: str = "") -> list[dict]:
    t = text.lower().strip()
    if not t:
        return rows
    words = t.split()
    return [r for r in rows if all(w in (r["task"] + " " + r["service"] + " " + " ".join(r.get("tags", []))).lower() for w in words)]


def render(rows: list[dict]) -> str:
    if not rows:
        return "No service matches. Run without --task to list everything."
    lines = [f"{'job':<34} {'service':<24} {'host':<30} {'lifecycle':<12} episode"]
    for r in rows:
        lines.append(f"{r['task']:<34} {r['service']:<24} {r['host']:<30} {r['lifecycle']:<12} {r.get('episode', '-')}")
    return "\n".join(lines)
