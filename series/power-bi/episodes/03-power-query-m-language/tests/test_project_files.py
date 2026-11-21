"""Validates the Power BI Project (PBIP) JSON files against Microsoft's published JSON schemas
(vendored in tests/schemas from developer.microsoft.com/json-schemas/fabric)."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

SRC = Path(__file__).resolve().parents[1] / "src"
SCHEMAS = Path(__file__).resolve().parent / "schemas"

CASES = [
    ("ContosoSales.pbip", "pbipProperties-1.0.0.json"),
    ("ContosoSales.Report/definition.pbir", "report-definitionProperties-2.0.0.json"),
    ("ContosoSales.SemanticModel/definition.pbism", "semanticModel-definitionProperties-1.0.0.json"),
    ("ContosoSales.Report/definition/version.json", "versionMetadata-1.0.0.json"),
    ("ContosoSales.Report/definition/report.json", "report-3.1.0.json"),
    ("ContosoSales.Report/definition/pages/pages.json", "pagesMetadata-1.1.0.json"),
    ("ContosoSales.Report/definition/pages/overview/page.json", "page-2.1.0.json"),
]


@pytest.mark.parametrize("file,schema", CASES)
def test_file_matches_published_schema(file, schema):
    doc = json.loads((SRC / file).read_text(encoding="utf-8"))
    sch = json.loads((SCHEMAS / schema).read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(sch).iter_errors(doc), key=str)
    assert not errors, "\n".join(e.message for e in errors)


def test_schema_url_in_each_file_matches_the_vendored_version():
    for file, schema in CASES:
        doc = json.loads((SRC / file).read_text(encoding="utf-8"))
        name = schema.rsplit("-", 1)[0]
        version = schema.rsplit("-", 1)[1].removesuffix(".json")
        assert f"/{version}/schema.json" in doc["$schema"], file
        assert name.split("-")[-1] in doc["$schema"], file


def test_report_points_to_the_semantic_model_by_relative_path():
    pbir = json.loads((SRC / "ContosoSales.Report/definition.pbir").read_text())
    target = (SRC / "ContosoSales.Report" / pbir["datasetReference"]["byPath"]["path"]).resolve()
    assert (target / "definition.pbism").exists()
    assert (target / "definition" / "model.tmdl").exists()


def test_pbism_version_supports_tmdl():
    pbism = json.loads((SRC / "ContosoSales.SemanticModel/definition.pbism").read_text())
    assert float(pbism["version"]) >= 4.0      # 4.0+ = TMDL definition folder allowed


def test_page_folder_name_matches_page_name():
    page_dir = SRC / "ContosoSales.Report/definition/pages/overview"
    assert json.loads((page_dir / "page.json").read_text())["name"] == page_dir.name
