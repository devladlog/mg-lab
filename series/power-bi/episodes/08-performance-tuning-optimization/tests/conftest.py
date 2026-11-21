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
for sub in ("tools", "data"):
    sys.path.insert(0, str(SRC / sub))

BEFORE = SRC / "ContosoPerf.Before.SemanticModel" / "definition"
AFTER = SRC / "ContosoPerf.After.SemanticModel" / "definition"
BEFORE_REPORT = SRC / "ContosoPerf.Before.Report"
AFTER_REPORT = SRC / "ContosoPerf.After.Report"


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


@pytest.fixture(scope="session")
def data200k(tmp_path_factory):
    """The 200,000-line export the expected/ numbers were made from."""
    import gen_sales
    folder = tmp_path_factory.mktemp("export200k")
    gen_sales.generate(folder, 200_000)
    return folder


@pytest.fixture(scope="session")
def data20k(tmp_path_factory):
    import gen_sales
    folder = tmp_path_factory.mktemp("export20k")
    gen_sales.generate(folder, 20_000)
    return folder
