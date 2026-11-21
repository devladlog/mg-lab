"""Every .sql file parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar), plus the claims the
episode makes: the procedures are transactional and safe to re-run, the catalog calls follow Learn's order and
parameter types, nothing contains a secret, the schema file is an unchanged copy of episode 5's."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import etl_lab as lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")
SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODE5 = ROOT.parent / "05-stored-procedures-functions"


def statements(name):
    return [st for b in tsqlparse.parse_all_sql()[name]["batches"] for st in b["statements"]]


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert statements(name)


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("EXEC catalog.create_execution @folder_name = ;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not EPISODE5.exists(), reason="episode 5 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode5():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODE5 / "src" / "sql" / "01-schema-and-data.sql").read_bytes()


def test_the_merge_procedure_is_transactional_and_checks_its_run():
    m = tsqlparse.modules()["Etl.usp_MergePartnerSales"]
    assert m["kind"] == "procedure"
    assert [p["name"] for p in m["parameters"]] == ["@ExecutionId"] and m["parameters"][0]["type"] == "bigint"
    assert "XactAbort=ON" in m["body"]["setOptions"] and "NoCount=ON" in m["body"]["setOptions"]
    types = set(m["body"]["nodeTypes"])
    assert {"BeginTransactionStatement", "CommitTransactionStatement", "ThrowStatement"} <= types


def test_prepare_procedure_takes_the_two_values_the_package_passes():
    m = tsqlparse.modules()["Etl.usp_PrepareLoad"]
    assert [(p["name"], p["type"]) for p in m["parameters"]] == [("@ExecutionId", "bigint"), ("@SourceFile", "nvarchar(260)")]


def test_run_script_uses_the_documented_catalog_calls_in_order():
    text = [st["text"] for st in statements("c02-run-package.sql") if st["type"] == "ExecuteStatement"]
    procs = [re.match(r"EXEC(?:UTE)?\s+([\w.]+)", t, re.I).group(1) for t in text]
    assert procs == ["catalog.create_execution", "catalog.set_execution_parameter_value", "catalog.set_execution_parameter_value",
                     "catalog.set_execution_parameter_value", "catalog.start_execution"]
    joined = "\n".join(text)
    assert re.search(r"@object_type = 50, @parameter_name = N'LOGGING_LEVEL'", joined)      # Learn: 50 for LOGGING_LEVEL, SYNCHRONIZED ...
    assert re.search(r"@object_type = 50, @parameter_name = N'SYNCHRONIZED'", joined)
    assert re.search(r"@object_type = 30, @parameter_name = N'InputFile'", joined)          # ... and 30 for a package parameter


def test_run_script_templates_cover_the_three_runs():
    for run in lab.RUNS:
        t = lab.run_script_text(run)
        assert f"@LoggingLevel smallint = {run.logging_level};" in t and run.file in t


def test_environment_script_references_the_variable_by_name():
    t = (SQL / "c01-environment.sql").read_text(encoding="utf-8")
    assert "@value_type = 'R'" in t and "@parameter_value = N'ServerName'" in t and "@reference_type = 'R'" in t


def test_deploy_script_reads_the_ispac_as_a_single_blob():
    t = (SQL / "c00-deploy-project.sql").read_text(encoding="utf-8")
    assert "SINGLE_BLOB" in t and "catalog.deploy_project" in t and "@project_stream" in t


def test_cleanup_removes_project_then_environment_then_folder():
    t = (SQL / "c99-catalog-cleanup.sql").read_text(encoding="utf-8")
    assert [t.index(x) for x in ("catalog.delete_project", "catalog.delete_environment", "catalog.delete_folder")] == sorted(
        t.index(x) for x in ("catalog.delete_project", "catalog.delete_environment", "catalog.delete_folder"))


def test_no_secrets_and_no_real_identifiers():
    for f in list(SQL.glob("*.sql")) + list((ROOT / "src").glob("*.py")) + list((ROOT / "data").glob("*.csv")):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"(?i)\b(pwd|password)\s*=\s*['\w]", text), f.name
        assert "onmicrosoft" not in text.lower(), f.name
