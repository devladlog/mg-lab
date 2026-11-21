import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from formatlint.expr import Date  # noqa: E402


@pytest.fixture
def formats():
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (SRC / "formats").glob("*.json")}


@pytest.fixture
def sample():
    data = json.loads((SRC / "sample-rows.json").read_text(encoding="utf-8"))
    rows = {}
    for r in data["rows"]:
        row = dict(r)
        row["DueDate"] = Date.parse(r["DueDate"]) if r["DueDate"] else ""
        rows[r["LinkTitle"].split(" #")[0]] = row
    return {"now": Date.parse(data["now"]), "me": data["me"], "rows": rows}
