"""Validate the formats against Microsoft's published JSON schemas (draft-04, with remote $refs).
Schemas are downloaded once into tests/.schema-cache; without network access these tests are skipped."""
import json
import re
import urllib.request
from pathlib import Path

import pytest
from jsonschema import Draft4Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT4

from conftest import SRC
from formatlint.expr import parse_excel

CACHE = Path(__file__).parent / ".schema-cache"


def fetch(uri: str) -> dict:
    uri = uri.split("#")[0]
    path = CACHE / re.sub(r"[^\w.-]", "_", uri)
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        try:
            body = urllib.request.urlopen(uri, timeout=20).read()
        except OSError as e:
            pytest.skip(f"schema not reachable ({e})")
        path.write_bytes(body)
    return json.loads(path.read_text(encoding="utf-8"))


# The view schema URL used in Learn's view-formatting examples points additionalRowClass at
# "...column-formatting.schema.json#definitions/expression" (no slash after '#'), which strict validators reject
# as an invalid JSON pointer. Microsoft also publishes a v2 view schema with valid pointers; validate against that.
LEGACY_VIEW = "https://developer.microsoft.com/json-schemas/sp/view-formatting.schema.json"
V2_VIEW = "https://developer.microsoft.com/json-schemas/sp/v2/view-formatting.schema.json"


def test_the_v2_schema_rejects_an_excel_style_row_class():
    fmt = json.loads((SRC / "formats" / "open-requests.view.json").read_text(encoding="utf-8"))
    errors = list(validator_for(V2_VIEW).iter_errors(fmt))
    assert any("is not of type 'object'" in e.message for e in errors)


def test_the_legacy_view_schema_has_an_invalid_pointer():
    ref = fetch(LEGACY_VIEW)["properties"]["additionalRowClass"]["$ref"]
    assert ref.endswith("#definitions/expression")


def validator_for(schema_uri: str) -> Draft4Validator:
    schema_uri = V2_VIEW if schema_uri == LEGACY_VIEW else schema_uri
    registry = Registry(retrieve=lambda uri: Resource.from_contents(fetch(uri), default_specification=DRAFT4))
    return Draft4Validator(fetch(schema_uri), registry=registry)


GOOD = sorted(p.name for p in (SRC / "formats").glob("*.json") if p.name != "map.json")


@pytest.mark.parametrize("name", GOOD)
def test_format_matches_microsoft_schema(name):
    fmt = json.loads((SRC / "formats" / name).read_text(encoding="utf-8"))
    if isinstance(fmt.get("additionalRowClass"), str):
        # Both published view schemas type additionalRowClass as an AST object only, while Learn's own examples
        # use an Excel-style string. Our parser checks that string; the schema checks everything else.
        parse_excel(fmt.pop("additionalRowClass"))
    errors = list(validator_for(fmt["$schema"]).iter_errors(fmt))
    assert errors == [], [e.message for e in errors]


def test_schema_rejects_a_view_format_declared_as_a_column_format():
    fmt = json.loads((SRC / "formats" / "bad" / "overdue-row.view.json").read_text(encoding="utf-8"))
    errors = list(validator_for(fmt["$schema"]).iter_errors(fmt))
    assert any("additionalRowClass" in e.message for e in errors)
