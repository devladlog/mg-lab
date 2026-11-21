import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCHEMAS = Path(__file__).resolve().parent / "schemas"
BASE = "https://developer.microsoft.com/json-schemas/"
sys.path.insert(0, str(SRC / "tools"))

MODEL = SRC / "ContosoSalesIR.SemanticModel" / "definition"
REPORT = SRC / "ContosoSalesIR.Report"
DAILY = ROOT / "expected" / "daily-2m.json"


def _retrieve(uri):
    if not uri.startswith(BASE):
        raise LookupError(uri)
    return Resource.from_contents(json.loads((SCHEMAS / uri[len(BASE):]).read_text(encoding="utf-8")))


REGISTRY = Registry(retrieve=_retrieve)


def schema_errors(doc):
    """Validate a PBIR/PBIP JSON document against the vendored copy of the schema its $schema names."""
    url = doc["$schema"]
    schema = json.loads((SCHEMAS / url[len(BASE):]).read_text(encoding="utf-8"))
    return sorted(Draft7Validator(schema, registry=REGISTRY).iter_errors(doc), key=str)


@pytest.fixture
def model_copy(tmp_path):
    """A writable copy of the model's TMDL folder, to break on purpose."""
    import shutil
    dst = tmp_path / "definition"
    shutil.copytree(MODEL, dst)
    return dst
