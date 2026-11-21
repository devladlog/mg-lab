"""The two Power BI projects: the model owner's (model + report) and the thin report (live connection)."""
import json
import re
import subprocess
import sys

import pytest

import report_lint as rl
from conftest import SRC, schema_errors

REPORT = SRC / "ContosoSales.Report"
THIN = SRC / "thin-report"
MODEL = SRC / "ContosoSales.SemanticModel" / "definition"
TMDL_LOAD = SRC / "TmdlLoad" / "bin" / "Debug" / "net8.0" / "tmdl-load.dll"
needs_tom = pytest.mark.skipif(not TMDL_LOAD.exists(), reason="build tmdl-load first: dotnet build src/TmdlLoad -m:1")


def pbir_files(report):
    return sorted(p for p in report.rglob("*.json") if "StaticResources" not in p.parts)


ALL_JSON = pbir_files(REPORT) + pbir_files(THIN / "StoreManagers.Report") + [
    SRC / "ContosoSales.pbip", THIN / "StoreManagers.pbip", SRC / "ContosoSales.SemanticModel/definition.pbism"]


def test_reports_match_the_layout_spec():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", ALL_JSON, ids=lambda p: str(p.relative_to(SRC)))
def test_file_matches_its_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_both_reports_are_lint_clean_against_the_shared_model():
    assert rl.lint(REPORT, MODEL) == []
    assert rl.lint(THIN / "StoreManagers.Report", MODEL) == []


def test_the_owner_report_is_bound_by_path_and_the_thin_report_by_connection():
    owner = json.loads((REPORT / "definition.pbir").read_text())["datasetReference"]
    thin = json.loads((THIN / "StoreManagers.Report" / "definition.pbir").read_text())["datasetReference"]
    assert owner == {"byPath": {"path": "../ContosoSales.SemanticModel"}}
    assert list(thin) == ["byConnection"]
    cs = thin["byConnection"]["connectionString"]
    assert cs == "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Contoso Data (Lab);Initial Catalog=ContosoSales"
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", cs)                     # no IDs in the repo


def test_the_thin_report_folder_holds_a_report_and_no_model():
    assert sorted(p.name for p in THIN.iterdir()) == ["StoreManagers.Report", "StoreManagers.pbip"]
    assert not list(THIN.rglob("*.tmdl")) and not list(THIN.rglob("*.pbism"))


def test_thin_report_uses_only_fields_the_shared_model_has_and_adds_no_measures():
    report_json = json.loads((THIN / "StoreManagers.Report" / "definition" / "report.json").read_text())
    assert "reportExtensions" not in report_json and not list((THIN / "StoreManagers.Report").rglob("reportExtensions.json"))
    page = json.loads((THIN / "StoreManagers.Report" / "definition" / "pages" / "pages.json").read_text())
    assert page["pageOrder"] == ["stores"]


def test_the_model_reads_no_local_file_so_it_needs_no_gateway():
    for f in MODEL.rglob("*.tmdl"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\b(File\.Contents|Folder\.Files|Folder\.Contents|Csv\.Document)\b", text), f.name
        if "partition" in text:
            assert "PowerPlatform.Dataflows(null)" in text, f.name


def test_parameters_are_placeholders_never_real_ids():
    text = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    ids = dict(re.findall(r'expression (\w+) = "([^"]*)"', text))
    assert ids == {"WorkspaceId": "00000000-0000-0000-0000-000000000000",
                   "DataflowId": "00000000-0000-0000-0000-000000000000", "UpnDomain": "contoso.com"}
    assert "DataFolder" not in text


def test_rls_roles_travel_with_the_shared_model():
    assert sorted(p.stem for p in (MODEL / "roles").glob("*.tmdl")) == ["Head Office", "Store Managers"]
    assert "USERPRINCIPALNAME()" in (MODEL / "roles" / "Store Managers.tmdl").read_text(encoding="utf-8")


def test_date_columns_show_business_names_over_contract_names():
    text = (MODEL / "tables" / "Date.tmdl").read_text(encoding="utf-8")
    assert "column 'Month Number'" in text and "sourceColumn: MonthNumber" in text
    assert "sortByColumn: 'Year Month Number'" in text


@needs_tom
def test_tom_loads_the_model_folder():
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(MODEL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "6 table(s), 3 parameter(s), 5 relationship(s), 2 role(s): loaded" in r.stdout
    assert re.search(r"table Store Access\s+2 columns.*entity StoreAccess", r.stdout)


@needs_tom
def test_tom_rejects_a_broken_folder(tmp_path):
    import shutil
    bad = tmp_path / "definition"
    shutil.copytree(MODEL, bad)
    (bad / "tables" / "Store.tmdl").write_text("table Store\n\tcolumn\n\t\tdataType: nonsense\n", encoding="utf-8")
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "ERROR" in r.stdout
