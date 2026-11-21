"""Every .sql file parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar) plus the claims the episode makes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import rpt_lab as lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")
SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODE5 = ROOT.parent / "05-stored-procedures-functions"


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert [st for b in f["batches"] for st in b["statements"]]


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("SELECT FROM WHERE;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not EPISODE5.exists(), reason="episode 5 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode5():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODE5 / "src" / "sql" / "01-schema-and-data.sql").read_bytes()


def test_report_procedures_have_the_parameters_the_rdl_passes():
    mods = tsqlparse.modules()
    sp = mods["Rpt.usp_SalesByProduct"]
    assert [p["name"] for p in sp["parameters"]] == ["@From", "@To", "@Region"]
    assert [p["type"] for p in sp["parameters"]][:2] == ["date", "date"]
    assert mods["Rpt.usp_Regions"]["parameters"] == []
    assert "NoCount=ON" in sp["body"]["setOptions"]


def test_reader_gets_execute_on_the_schema_and_nothing_else():
    text = (SQL / "r02-reader-login.sql").read_text(encoding="utf-8")
    grants = re.findall(r"^\s*(GRANT|DENY|ALTER ROLE|EXEC sp_addrolemember)\b.*$", text, re.M | re.I)
    assert re.findall(r"^\s*GRANT .*$", text, re.M) == ["GRANT EXECUTE ON SCHEMA::Rpt TO rs_reader;"]
    assert "db_datareader" not in text and "sysadmin" not in text and len(grants) == 1


def test_no_secret_in_any_sql_file():
    for name in SQL_FILES:
        text = (SQL / name).read_text(encoding="utf-8")
        assert not re.search(r"PASSWORD\s*=\s*N'[^<'][^']*'(?!\s*\+)", text, re.I), name


def test_reset_drops_database_and_login_only():
    text = (SQL / "r00-reset.sql").read_text(encoding="utf-8")
    assert re.findall(r"DROP (\w+) (\w+)", text) == [("DATABASE", "ContosoBikesRpt"), ("LOGIN", "rs_reader")]


def test_query_markers_are_balanced():
    text = (SQL / "r01-report-objects.sql").read_text(encoding="utf-8")
    assert len(re.findall(r"^\s*-- query-begin\s*$", text, re.M)) == len(re.findall(r"^\s*-- query-end\s*$", text, re.M)) == 2
