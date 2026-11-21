import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import MODEL, REPORT, ROOT, SRC, schema_errors

PQ_LINT = SRC / "pq-lint" / "dist" / "src" / "cli.js"
TMDL_LOAD = SRC / "TmdlLoad" / "bin" / "Debug" / "net10.0" / "tmdl-load.dll"
needs_pq_lint = pytest.mark.skipif(not PQ_LINT.exists(), reason="build pq-lint first: cd src/pq-lint && npm ci && npm test")
needs_tom = pytest.mark.skipif(not TMDL_LOAD.exists() or not shutil.which("dotnet"), reason="build tmdl-load first: dotnet build src/TmdlLoad -m:1")


def test_project_files_validate_against_the_microsoft_schemas():
    docs = [SRC / "ContosoSalesIR.pbip", SRC / "ContosoSalesIR.SemanticModel" / "definition.pbism", REPORT / "definition.pbir"]
    docs += sorted(p for p in (REPORT / "definition").rglob("*.json"))
    assert len(docs) == 3 + 3 + 1 + 5 + 1 - 1 + 1 or len(docs) >= 10
    for p in docs:
        errors = schema_errors(json.loads(p.read_text(encoding="utf-8")))
        assert not errors, f"{p.name}: {errors[0].message}"


def test_report_matches_the_generator_spec():
    r = subprocess.run(["python3", str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_report_is_bound_to_the_model_and_uses_only_its_fields():
    ref = json.loads((REPORT / "definition.pbir").read_text(encoding="utf-8"))["datasetReference"]["byPath"]["path"]
    assert (REPORT / ref).resolve() == (SRC / "ContosoSalesIR.SemanticModel").resolve()
    text = (MODEL / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
    seen = 0
    for p in (REPORT / "definition" / "pages").rglob("visual.json"):
        v = json.loads(p.read_text(encoding="utf-8"))
        props = v["visual"]["visualContainerObjects"]
        assert props["title"][0]["properties"]["text"] and props["general"][0]["properties"]["altText"]
        for role in v["visual"]["query"]["queryState"].values():
            for proj in role["projections"]:
                prop = list(proj["field"].values())[0]["Property"]
                assert f"measure '{prop}'" in text or f"measure {prop} " in text or f"column '{prop}'" in text, prop
                seen += 1
    assert seen == 6


def test_source_expression_is_the_partition_query():
    import re
    t = (MODEL / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
    pol_expr = t.split("sourceExpression =\n")[1].split("\n\n")[0]
    part_expr = t.split("\tpartition Sales = m\n")[1].split("source =\n")[1]
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    assert norm(pol_expr) == norm(part_expr)


def test_parameters_and_policy_values():
    exp = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    assert 'expression RangeStart = #datetime(2026, 11, 1, 0, 0, 0) meta [IsParameterQuery=true, Type="DateTime"' in exp
    assert 'expression RangeEnd = #datetime(2026, 11, 8, 0, 0, 0) meta [IsParameterQuery=true, Type="DateTime"' in exp
    t = (MODEL / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
    for line in ("policyType: basic", "rollingWindowGranularity: year", "rollingWindowPeriods: 3", "incrementalGranularity: day", "incrementalPeriods: 10"):
        assert f"\t\t{line}\n" in t
    assert "devladlog" not in (exp + t).lower()


@needs_pq_lint
def test_every_expression_parses_with_microsofts_parser(tmp_path):
    subprocess.run(["python3", str(SRC / "tools" / "extract_m.py"), str(MODEL), str(tmp_path)], check=True, capture_output=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["RangeEnd.pq", "RangeStart.pq", "Sales.pollingExpression.pq", "Sales.pq", "Sales.sourceExpression.pq", "SqlDatabase.pq", "SqlServer.pq"]
    r = subprocess.run(["node", str(PQ_LINT), str(tmp_path), "--strict"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "7 queries: 0 error(s), 0 warning(s)" in r.stdout


@needs_tom
def test_the_tabular_object_model_loads_the_model_and_the_policy():
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(MODEL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "refresh policy: Import, keep 3 Year(s), refresh 10 Day(s), offset 0, detect data changes" in r.stdout
    assert "1 table(s), 4 parameter(s), 0 other expression(s)" in r.stdout


@needs_tom
def test_tom_rejects_a_broken_folder(tmp_path):
    (tmp_path / "model.tmdl").write_text("model Model\n\tnot a property ::\n", encoding="utf-8")
    assert subprocess.run(["dotnet", str(TMDL_LOAD), str(tmp_path)], capture_output=True, text=True).returncode == 1
