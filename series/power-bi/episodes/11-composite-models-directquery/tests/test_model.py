"""The PBIP skeleton against Microsoft's JSON schemas, the TMDL through the Tabular Object Model (composite-lint), and mutated copies."""
import json
import re
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from conftest import SRC

SCHEMAS = Path(__file__).resolve().parent / "schemas"
MODEL = SRC / "ContosoSalesComposite.SemanticModel" / "definition"
CASES = [
    ("ContosoSalesComposite.pbip", "pbipProperties-1.0.0.json"),
    ("ContosoSalesComposite.Report/definition.pbir", "report-definitionProperties-2.0.0.json"),
    ("ContosoSalesComposite.SemanticModel/definition.pbism", "semanticModel-definitionProperties-1.0.0.json"),
    ("ContosoSalesComposite.Report/definition/version.json", "versionMetadata-1.0.0.json"),
    ("ContosoSalesComposite.Report/definition/report.json", "report-3.1.0.json"),
    ("ContosoSalesComposite.Report/definition/pages/pages.json", "pagesMetadata-1.1.0.json"),
    ("ContosoSalesComposite.Report/definition/pages/overview/page.json", "page-2.1.0.json"),
]


@pytest.mark.parametrize("file,schema", CASES)
def test_file_matches_published_schema(file, schema):
    doc = json.loads((SRC / file).read_text(encoding="utf-8"))
    sch = json.loads((SCHEMAS / schema).read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(sch).iter_errors(doc), key=str)
    assert not errors, "\n".join(e.message for e in errors)


def test_sql_column_names_in_tmdl_exist_in_the_generated_tables():
    sql = (SRC / "sql" / "01-create-database.sql").read_text(encoding="utf-8")
    for tmdl, table in (("Sales", "FactSales"), ("Customer", "DimCustomer"), ("Store", "DimStore"), ("Product", "DimProduct"), ("Date", "DimDate")):
        text = (MODEL / "tables" / f"{tmdl}.tmdl").read_text(encoding="utf-8")
        assert f'Item = "{table}"' in text
        for col in re.findall(r"sourceColumn: (\w+)", text):
            assert re.search(rf"\b{col}\b", sql), f"{tmdl}: {col}"
    agg = (MODEL / "tables" / "Sales Agg.tmdl").read_text(encoding="utf-8")
    assert 'Item = "vwSalesAgg"' in agg
    view = (SRC / "sql" / "03-agg-view.sql").read_text(encoding="utf-8")
    for col in re.findall(r"sourceColumn: (\w+)", agg):
        assert re.search(rf"\b{col}\b", view), col


def test_no_secrets_or_real_hosts_in_the_model():
    for p in MODEL.rglob("*.tmdl"):
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"password|pwd=|secret", t, re.I), p
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", t), p


def test_composite_lint_is_clean_on_the_real_model(run_lint):
    rc, out = run_lint(MODEL)
    assert rc == 0, out
    assert "0 error(s), 0 warning(s)" in out


def test_explain_predicts_hits_and_the_two_misses(run_lint):
    rc, out = run_lint(MODEL, explain=True)
    assert rc == 0, out
    assert re.search(r"measure \[Sales Amount\]\s+HIT", out)
    assert re.search(r"measure \[Orders\]\s+MISS", out)
    assert re.search(r"group by Customer\[\.\.\.\]\s+MISS", out)
    assert re.search(r"group by Date\[\.\.\.\]\s+HIT", out)


def mutated(tmp_path, file, old, new):
    dst = tmp_path / "definition"
    shutil.copytree(MODEL, dst)
    p = dst / file
    text = p.read_text(encoding="utf-8")
    assert old in text, (file, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return dst


def test_detail_table_in_import_mode_is_an_error(tmp_path, run_lint):
    rc, out = run_lint(mutated(tmp_path, "tables/Sales.tmdl", "mode: directQuery", "mode: import"))
    assert rc == 1 and "CM002" in out and "must be DirectQuery" in out


def test_visible_aggregation_table_is_a_warning(tmp_path, run_lint):
    rc, out = run_lint(mutated(tmp_path, "tables/Sales Agg.tmdl", "table 'Sales Agg'\n\tisHidden\n", "table 'Sales Agg'\n"))
    assert "CM003" in out


def test_import_dimension_next_to_a_directquery_fact_makes_limited_relationships(tmp_path, run_lint):
    rc, out = run_lint(mutated(tmp_path, "tables/Date.tmdl", "mode: dual", "mode: import"))
    assert "CM001" in out and "limited" in out
