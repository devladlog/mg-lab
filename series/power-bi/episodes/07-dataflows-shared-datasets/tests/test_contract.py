"""The contract between the dataflow and the shared model: what it says, who keeps it, how it breaks."""
import copy
import json
import re
import shutil
import subprocess
import sys

import pytest

import check_contract as cc
import pq_reference as ref
from conftest import SRC

MODEL = SRC / "ContosoSales.SemanticModel" / "definition"
QUERIES = SRC / "dataflow" / "queries"
CONTRACT = json.loads((SRC / "dataflow" / "contract.json").read_text(encoding="utf-8"))
SITE = SRC / "data" / "ContosoBikesData"
PY_TYPES = {"int64": int, "text": str, "date": __import__("datetime").date, "currency": __import__("decimal").Decimal}


def rules(findings, severity=None):
    return sorted({f["rule"] for f in findings if severity in (None, f["severity"])})


def test_the_model_matches_the_contract():
    f = cc.check(MODEL, CONTRACT, QUERIES)
    assert rules(f, "error") == []
    assert [(x["rule"], x["where"]) for x in f] == [("DC005", "Store Access")]    # UserAlias: the model derives the UPN from it


def test_command_line_exit_codes(tmp_path):
    ok = subprocess.run([sys.executable, str(SRC / "tools" / "check_contract.py"), "--model", str(MODEL)], capture_output=True, text=True)
    assert ok.returncode == 0 and "0 error(s)" in ok.stdout
    bad = tmp_path / "definition"
    shutil.copytree(MODEL, bad)
    t = bad / "tables" / "Product.tmdl"
    t.write_text(t.read_text().replace("sourceColumn: Category", "sourceColumn: ProductCategory"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SRC / "tools" / "check_contract.py"), "--model", str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "DC003" in r.stdout and "ProductCategory" in r.stdout


def mutated_contract(entity, fn):
    c = copy.deepcopy(CONTRACT)
    fn(c["entities"][entity])
    return c


def test_a_column_renamed_in_the_dataflow_breaks_the_model_before_refresh_does():
    c = mutated_contract("Product", lambda cols: cols[4].update(name="ProductCategory"))
    f = cc.check(MODEL, c, QUERIES)
    assert ("DC003", "Product[Category]") in [(x["rule"], x["where"]) for x in f]


def test_a_dropped_entity_is_reported():
    c = copy.deepcopy(CONTRACT)
    del c["entities"]["Store"]
    assert "DC002" in rules(cc.check(MODEL, c, QUERIES), "error")


def test_a_changed_type_is_reported():
    c = mutated_contract("Sales", lambda cols: cols[7].update(type="text"))          # Quantity: int64 -> text
    f = [x for x in cc.check(MODEL, c, QUERIES) if x["rule"] == "DC004"]
    assert [x["where"] for x in f] == ["Sales[Quantity]"]


def test_names_with_spaces_break_the_naming_rule():
    c = mutated_contract("Date", lambda cols: cols[3].update(name="Month Number"))
    assert "DC007" in rules(cc.check(MODEL, c, QUERIES), "error")


def test_hard_coded_ids_are_reported(tmp_path):
    bad = tmp_path / "definition"
    shutil.copytree(MODEL, bad)
    t = bad / "tables" / "Store.tmdl"
    t.write_text(t.read_text().replace("workspaceId = WorkspaceId", 'workspaceId = "11111111-2222-3333-4444-555555555555"'), encoding="utf-8")
    f = cc.check(bad, CONTRACT, QUERIES)
    assert [(x["rule"], x["where"]) for x in f if x["rule"] == "DC008"] == [("DC008", "Store")]


def test_a_table_that_still_reads_files_is_reported(tmp_path):
    bad = tmp_path / "definition"
    shutil.copytree(MODEL, bad)
    t = bad / "tables" / "Store.tmdl"
    t.write_text(re.sub(r"(?s)source =\n.*\Z", lambda m: 'source =\n\t\t\t\tCsv.Document(File.Contents("C:\\data\\dim_store.csv"))\n', t.read_text()), encoding="utf-8")
    assert "DC001" in rules(cc.check(bad, CONTRACT, QUERIES), "error")


def test_query_files_and_contract_must_list_the_same_queries(tmp_path):
    q = tmp_path / "queries"
    shutil.copytree(QUERIES, q)
    (q / "Extra.pq").write_text("1", encoding="utf-8")
    (q / "Store.pq").unlink()
    f = [x["where"] for x in cc.check(MODEL, CONTRACT, q) if x["rule"] == "DC006"]
    assert f == ["Store", "Extra"] or sorted(f) == ["Extra", "Store"]


# ---- the contract describes what the queries produce (the Python mirror follows the M step by step) ----------------
@pytest.fixture(scope="module")
def tables():
    return ref.build(SITE / "exports", SITE / "security")


@pytest.mark.parametrize("entity", list(CONTRACT["entities"]))
def test_the_mirror_publishes_exactly_the_contract_columns_in_order(tables, entity):
    declared = CONTRACT["entities"][entity]
    row = tables[entity][0]
    assert list(row) == [c["name"] for c in declared]
    for c in declared:
        assert isinstance(row[c["name"]], PY_TYPES[c["type"]]), (entity, c)


@pytest.mark.parametrize("entity", [e for e, cols in CONTRACT["entities"].items() if any("from" in c for c in cols)])
def test_renamed_columns_remember_their_old_name(entity):
    for c in CONTRACT["entities"][entity]:
        if "from" in c:
            assert c["from"].replace(" ", "").lower() == c["name"].lower()


def test_staging_queries_are_not_published():
    assert not set(CONTRACT["staging"]) & set(CONTRACT["entities"])
    assert set(CONTRACT["parameters"]) == {"ExportSite"}
