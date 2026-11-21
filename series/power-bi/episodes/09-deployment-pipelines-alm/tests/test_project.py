import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import MODEL, REPORT, ROOT, SRC, STAGES, schema_errors

PQ_LINT = SRC / "pq-lint" / "dist" / "src" / "cli.js"
TMDL_LOAD = SRC / "TmdlLoad" / "bin" / "Debug" / "net10.0" / "tmdl-load.dll"
needs_pq_lint = pytest.mark.skipif(not PQ_LINT.exists(), reason="build pq-lint first: cd src/pq-lint && npm ci && npm test")
needs_tom = pytest.mark.skipif(not TMDL_LOAD.exists() or not shutil.which("dotnet"),
                               reason="build tmdl-load first: dotnet build src/TmdlLoad -m:1")


def all_json(folder):
    return sorted(p for p in folder.rglob("*.json") if "StaticResources" not in p.parts)


def test_project_files_validate_against_the_microsoft_schemas():
    docs = [SRC / "ContosoSales.pbip", ROOT / "src" / "ContosoSales.SemanticModel" / "definition.pbism", REPORT / "definition.pbir"]
    docs += all_json(REPORT / "definition")
    assert len(docs) == 3 + 1 + 1 + 1 + 1 + 5 + 1 - 1 + 0 or len(docs) > 8
    for p in docs:
        errors = schema_errors(json.loads(p.read_text(encoding="utf-8")))
        assert not errors, f"{p.name}: {errors[0].message}"


def test_report_matches_the_generator_spec():
    r = subprocess.run(["python3", str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_every_visual_has_title_alt_text_and_a_unique_tab_order():
    orders = []
    for p in (REPORT / "definition" / "pages").rglob("visual.json"):
        v = json.loads(p.read_text(encoding="utf-8"))
        props = v["visual"]["visualContainerObjects"]
        assert props["title"][0]["properties"]["text"]
        assert props["general"][0]["properties"]["altText"]
        orders.append(v["position"]["tabOrder"])
    assert len(orders) == 5 and len(set(orders)) == 5


def test_report_is_bound_to_the_model_beside_it():
    ref = json.loads((REPORT / "definition.pbir").read_text(encoding="utf-8"))["datasetReference"]["byPath"]["path"]
    assert (REPORT / ref).resolve() == (SRC / "ContosoSales.SemanticModel").resolve()


def test_report_uses_only_fields_the_model_has():
    text = (MODEL / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
    for p in (REPORT / "definition" / "pages").rglob("visual.json"):
        v = json.loads(p.read_text(encoding="utf-8"))
        for role in v["visual"]["query"]["queryState"].values():
            for proj in role["projections"]:
                prop = list(proj["field"].values())[0]["Property"]
                assert (f"measure '{prop}'" in text or f"measure {prop} " in text or f"column '{prop}'" in text
                        or f"column {prop}\n" in text), prop


def test_the_stage_values_are_parameters_with_defaults_for_development():
    text = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    assert 'expression ExportsFolder = "exports-sample"' in text
    assert 'expression StageName = "DEV"' in text
    # no tenant name or real site anywhere
    assert "devladlog" not in text.lower()


def test_stages_json_matches_the_model_and_the_expected_values():
    import expected
    stages = json.loads(STAGES.read_text(encoding="utf-8"))
    assert [s["order"] for s in stages["stages"]] == [0, 1, 2]
    assert "parameterRules" not in stages["stages"][0]                   # rules can't be created in Development
    for s, key in zip(stages["stages"][1:], ("TEST", "PROD")):
        assert s["parameterRules"]["ExportsFolder"] == expected.STAGES[key]
        assert s["parameterRules"]["StageName"] == key
    assert expected.STAGES["DEV"] == "exports-sample"


def test_expected_stage_values():
    import expected
    e = expected.expected()
    assert e["DEV"]["files"] == 3 and e["TEST"]["files"] == 24
    assert (e["DEV"]["sales_amount"], e["DEV"]["orders"], e["DEV"]["order_lines"]) == ("220652.08", 283, 478)
    # the same star as episodes 3 and 7: Sales Amount 1,862,401.98, Orders 2,440, 4,071 lines
    assert (e["TEST"]["sales_amount"], e["TEST"]["orders"], e["TEST"]["order_lines"]) == ("1862401.98", 2440, 4071)
    assert e["TEST"] == {**e["PROD"]}
    assert Decimal(e["DEV"]["sales_amount"]) < Decimal(e["TEST"]["sales_amount"])


def test_the_sample_folder_holds_three_of_the_monthly_files_unchanged():
    root = SRC / "data" / "ContosoBikesData"
    sample = sorted(p.name for p in (root / "exports-sample").glob("*.csv"))
    assert sample == ["sales_2025-10.csv", "sales_2025-11.csv", "sales_2025-12.csv"]
    for n in sample:
        assert (root / "exports-sample" / n).read_bytes() == (root / "exports" / n).read_bytes()


@needs_pq_lint
def test_every_partition_and_expression_parses_with_microsofts_parser(tmp_path):
    subprocess.run(["python3", str(SRC / "tools" / "extract_m.py"), str(MODEL), str(tmp_path)], check=True, capture_output=True)
    r = subprocess.run(["node", str(PQ_LINT), str(tmp_path), "--strict"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "6 queries: 0 error(s), 0 warning(s)" in r.stdout


@needs_tom
def test_the_tabular_object_model_loads_the_model():
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(MODEL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "2 table(s), 3 parameter(s), 1 other expression(s)" in r.stdout


@needs_tom
def test_tom_rejects_a_broken_folder(tmp_path):
    (tmp_path / "model.tmdl").write_text("model Model\n\tnot a property ::\n", encoding="utf-8")
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 1


def test_ci_workflow_parses_and_has_no_secrets_or_sign_in():
    import yaml
    text = (SRC / "ci" / "pr-gate.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    assert set(wf["jobs"]) == {"model-checks", "pipeline-module"}
    assert wf["permissions"] == {"contents": "read"}
    assert "secrets." not in text and "Connect-PowerBIServiceAccount" not in text and "az login" not in text
    # every script the workflow calls exists
    for rel in ("src/tools/alm_check.py", "tests/PbiPipelines.Tests.ps1", "src/pipeline/stages.json"):
        assert (ROOT / rel).exists(), rel
