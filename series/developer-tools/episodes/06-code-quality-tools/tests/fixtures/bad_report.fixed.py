import os
from pathlib import Path

API_PASSWORD = os.environ.get("REPORT_API_PASSWORD", "")


def load(path, seen=None):
    seen = [] if seen is None else seen
    target = Path(path)
    data = target.read_text(encoding="utf-8") if target.exists() else ""
    seen.append(path)
    return {"path": path, "data": data, "flag": bool(data)}


def names(items: list[str]) -> list[str]:
    return [i.strip() for i in items]
