"""The column contract (columns.json) as Python: one source of truth for function, library and flow."""
import json
from pathlib import Path

CONTRACT_PATH = Path(__file__).with_name("columns.json")


def load_contract(path: Path = CONTRACT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTRACT = load_contract()
COLUMNS = {c["internalName"]: c for c in CONTRACT["columns"]}
STATUS_CHOICES = COLUMNS["InvStatus"]["choices"]

READY, NEEDS_REVIEW, REJECTED = "Ready", "Needs review", "Rejected"
assert {READY, NEEDS_REVIEW, REJECTED} <= set(STATUS_CHOICES), "columns.json and code disagree on statuses"
