"""The PBIR report: generated from the layout spec, valid against Microsoft's schemas, lint-clean, two pages."""
import json
import subprocess
import sys

import pytest

import report_lint as rl
from conftest import SRC, schema_errors

REPORT = SRC / "ContosoSales.Report"
MODEL = SRC / "ContosoSales.SemanticModel" / "definition"
PBIR_FILES = sorted(p for p in REPORT.rglob("*.json") if "StaticResources" not in p.parts)


def test_report_matches_the_layout_spec():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", PBIR_FILES + [SRC / "ContosoSales.pbip", SRC / "ContosoSales.SemanticModel/definition.pbism"],
                         ids=lambda p: str(p.relative_to(SRC)))
def test_file_matches_its_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_report_has_no_lint_findings_including_fields_that_exist_in_the_model():
    assert rl.lint(REPORT, MODEL) == []


def test_two_pages_overview_first():
    pages = json.loads((REPORT / "definition/pages/pages.json").read_text())
    assert pages["pageOrder"] == ["overview", "security"]
    assert json.loads((REPORT / "definition/pages/security/page.json").read_text())["displayName"] == "Store security"


def test_security_page_shows_identity_counts_stores_and_customers():
    visuals = {p.parent.name: json.loads(p.read_text()) for p in REPORT.glob("definition/pages/security/visuals/*/visual.json")}
    assert set(visuals) == {"kpiWho", "kpiStores", "kpiCustomers", "kpiSalesSecurity", "tableStores", "slicerCustomer"}
    who = visuals["kpiWho"]["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]
    assert who["Property"] == "Who Am I"
    assert visuals["slicerCustomer"]["visual"]["visualType"] == "slicer"


def test_overview_fills_the_free_cell_with_sales_by_store():
    bar = json.loads((REPORT / "definition/pages/overview/visuals/barStore/visual.json").read_text())
    assert bar["position"]["x"] == 24 + 104 * 6 and bar["position"]["y"] == 432
    cat = bar["visual"]["query"]["queryState"]["Category"]["projections"][0]["field"]["Column"]
    assert cat["Expression"]["SourceRef"]["Entity"] == "Store" and cat["Property"] == "Store"
