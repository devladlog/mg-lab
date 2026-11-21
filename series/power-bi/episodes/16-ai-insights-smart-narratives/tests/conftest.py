import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCHEMAS = Path(__file__).resolve().parent / "schemas"
MODEL = SRC / "ContosoSalesAI.SemanticModel" / "definition"
BASE = "https://developer.microsoft.com/json-schemas/"
for sub in ("", "data"):
    sys.path.insert(0, str(SRC / sub))


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
def star(tmp_path_factory):
    """The star schema and the order profile, regenerated from seed 42 (deterministic)."""
    import build_order_profile as bop
    import build_star
    import generate_export

    base = tmp_path_factory.mktemp("star")
    raw = base / "raw.csv"
    import csv
    with raw.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(generate_export.HEADER)
        w.writerows(generate_export.generate(42))
    out = base / "star"
    build_star.write(build_star.build(build_star.read_export(raw)), out)
    bop.write_profile(bop.build_profile(out), out)
    return out
