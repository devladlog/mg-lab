import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
KQL = SRC / "kql"
SCHEMAS = Path(__file__).resolve().parent / "schemas"
MODEL = SRC / "ContosoLive.SemanticModel" / "definition"
BASE = "https://developer.microsoft.com/json-schemas/"
sys.path.insert(0, str(SRC / "tillstream"))

T0 = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)  # a whole minute: the plan's minutes line up with 1m bins


def _retrieve(uri):
    if not uri.startswith(BASE):
        raise LookupError(uri)
    return Resource.from_contents(json.loads((SCHEMAS / uri[len(BASE):]).read_text(encoding="utf-8")))


REGISTRY = Registry(retrieve=_retrieve)


def schema_errors(doc):
    """Validate a PBIR/PBIP JSON document against the vendored copy of the schema its $schema names."""
    schema = json.loads((SCHEMAS / doc["$schema"][len(BASE):]).read_text(encoding="utf-8"))
    return sorted(Draft7Validator(schema, registry=REGISTRY).iter_errors(doc), key=str)


@pytest.fixture(scope="session")
def plan():
    import events
    return events.build_plan(seed=42, minutes=10, rate_per_min=30, run_id="demo17")


@pytest.fixture(scope="session")
def records(plan):
    """What a full run puts on the wire, as dicts, in send order."""
    import events
    return [events.to_record(e.sale, T0, "demo17") for e in plan]
