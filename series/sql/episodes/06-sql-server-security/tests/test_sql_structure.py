"""Every script parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar), plus the structural
claims the episode makes: concatenation vs sp_executesql, schema-bound predicates, grants to roles only,
no secrets in the repo, every EXECUTE AS undone by a REVERT."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import security_lab  # noqa: E402

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
    bad.write_text("CREATE SECURITY POLICY p ADD FILTER PREDICATE ON t;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not EPISODE5.exists(), reason="episode 5 folder not present")
@pytest.mark.parametrize("name", ["00-create-database.sql", "01-schema-and-data.sql", "02-functions.sql",
                                  "03-procedures.sql"])
def test_episode5_files_are_unchanged_copies(name):
    assert (SQL / name).read_bytes() == (EPISODE5 / "src" / "sql" / name).read_bytes()


@pytest.mark.skipif(not EPISODE5.exists(), reason="episode 5 folder not present")
@pytest.mark.parametrize("rel", ["src/labdb.py", "tools/TsqlParse/Program.cs", "tools/TsqlParse/TsqlParse.csproj"])
def test_shared_code_is_the_same_as_episode5(rel):
    assert (ROOT / rel).read_bytes() == (EPISODE5 / rel).read_bytes()


def test_unsafe_search_concatenates_input_into_code():
    p = tsqlparse.modules()["Sales.usp_SearchCustomers_Unsafe"]["body"]
    sql_var = next(v for v in p["variables"] if v["name"] == "@sql")
    assert "+ @NamePrefix +" in sql_var["value"]
    assert "sys.sp_executesql" not in p["procedureCalls"]
    assert "ExecutableStringList" in p["nodeTypes"]                 # EXEC (@sql)


def test_safe_search_keeps_input_as_a_parameter():
    p = tsqlparse.modules()["Sales.usp_SearchCustomers"]["body"]
    sql_var = next(v for v in p["variables"] if v["name"] == "@sql")
    assert "@NamePrefix" not in sql_var["value"] and "@prefix" in sql_var["value"]
    assert "QUOTENAME(@SortBy)" in sql_var["value"]
    assert p["procedureCalls"] == ["sys.sp_executesql"]
    assert "THROW 50010" in security_lab.sql_text("11-app-procedures.sql")   # the sort column whitelist


@pytest.mark.parametrize("proc", ["Sales.usp_SearchCustomers_Unsafe", "Sales.usp_SearchCustomers"])
def test_local_builder_reads_what_scriptdom_reads(proc):
    sql_var = next(v for v in tsqlparse.modules()[proc]["body"]["variables"] if v["name"] == "@sql")
    assert security_lab.sql_builder(proc) == sql_var["value"]


def test_rls_predicates_are_schema_bound_inline_functions():
    mods = tsqlparse.modules()
    for name in ("Security.fn_CustomerRegionPredicate", "Security.fn_OrderCustomerPredicate"):
        m = mods[name]
        assert m["kind"] == "inline table-valued function" and "SchemaBinding" in m["options"]
        assert {"USER_NAME", "IS_MEMBER"} <= set(m["body"]["functionCalls"])   # caller-based, with an admin bypass
    policy = [st for st in statements("15-row-level-security.sql") if st["type"] == "CreateSecurityPolicyStatement"]
    assert len(policy) == 1
    assert policy[0]["text"].count("ADD FILTER PREDICATE") == 2 and "STATE = ON" in policy[0]["text"]


def test_grants_go_to_roles_and_the_certificate_user_only():
    grants = [st["text"] for f in SQL_FILES for st in statements(f) if st["type"] == "GrantStatement"]
    assert len(grants) == 6
    for g in grants:
        grantee = re.search(r"\bTO\s+(\w+)\s*;?$", g).group(1)
        assert grantee in {"app_sales", "reporting", "search_signer"}, g
        if grantee == "app_sales":
            assert "ON OBJECT::Sales.usp_" in g or "ON TYPE::Sales.OrderLineList" in g, g   # never tables
    assert any("GRANT EXECUTE, REFERENCES ON TYPE::Sales.OrderLineList" in g for g in grants)  # TVP needs both


def test_signing_script_stores_no_password_and_drops_the_private_key():
    for f in SQL_FILES:
        # a literal password would be PASSWORD = '...'; the signing script only has PASSWORD = ' + QUOTENAME(@pw ...)
        assert not re.search(r"PASSWORD\s*=\s*N?'(?!\s*\+)", security_lab.sql_text(f), re.IGNORECASE), f
    types = [st["type"] for st in statements("14-sign-search-procedure.sql")]
    assert "AlterCertificateStatement" in types
    assert "REMOVE PRIVATE KEY" in security_lab.sql_text("14-sign-search-procedure.sql")
    assert "NEWID()" in security_lab.sql_text("14-sign-search-procedure.sql")


@pytest.mark.parametrize("name", [f for f in SQL_FILES if f.startswith("s")])
def test_every_impersonation_is_reverted(name):
    types = [st["type"] for st in statements(name)]
    assert types.count("ExecuteAsStatement") == types.count("RevertStatement")
    assert types[-1] == "SelectStatement"                         # the step's result set comes last


def test_masking_script_uses_the_email_function():
    alter = [st["text"] for st in statements("13-dynamic-data-masking.sql") if st["type"] == "AlterTableAlterColumnStatement"]
    assert alter == ["ALTER TABLE Sales.Customers ALTER COLUMN Email ADD MASKED WITH (FUNCTION = 'email()');"]
