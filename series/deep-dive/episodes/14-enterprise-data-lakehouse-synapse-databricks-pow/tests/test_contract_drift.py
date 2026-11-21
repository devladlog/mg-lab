"""Everything that is not Spark must agree with lakehouse/contract.py: a renamed column fails here, not in a report."""
import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

from lakehouse import medallion
from lakehouse.contract import GOLD_TABLES, LAYOUT

ROOT = Path(__file__).resolve().parents[1]
TSQL_TYPE = {"string": "varchar", "bigint": "bigint", "date": "date", "timestamp": "datetime2", "decimal": "decimal"}
TMDL_TYPE = {"string": "string", "bigint": "int64", "date": "dateTime", "timestamp": "dateTime", "decimal": "decimal"}


def kind(spark_type):
    return spark_type.split("(")[0]


def split_go(text):
    return [s.strip() for s in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if s.strip()]


# ------------------------------------------------------------------ Synapse serverless views
SQL = (ROOT / "src/synapse/serving.sql").read_text()
VIEW = re.compile(r"CREATE OR ALTER VIEW gold\.(\w+) AS(.*?)FROM OPENROWSET\((.*?)\)\s*WITH \((.*?)\) AS r;", re.S)


def test_serving_sql_parses_as_tsql():
    for stmt in split_go(SQL):
        body = re.sub(r"--[^\n]*", "", stmt)
        body = VIEW.sub(lambda m: f"CREATE OR ALTER VIEW gold.{m.group(1)} AS{m.group(2)}FROM delta_r AS r;", body)
        tree = sqlglot.parse_one(body, read="tsql")
        if body.lstrip().upper().startswith("CREATE OR ALTER VIEW"):
            assert isinstance(tree, exp.Create)


@pytest.mark.parametrize("table", GOLD_TABLES)
def test_serving_view_matches_gold_contract(table):
    views = {m.group(1): m for m in VIEW.finditer(SQL)}
    m = views[table]
    args = m.group(3)
    assert "FORMAT = 'DELTA'" in args and "DATA_SOURCE = 'lake'" in args
    assert f"BULK '{LAYOUT['gold_' + table]}'" in args            # root Delta folder, no wildcards
    assert "*" not in args
    cols = {}
    for line in m.group(4).strip().splitlines():
        name, rest = line.strip().rstrip(",").split(None, 1)
        cols[name] = rest
        if rest.startswith("varchar"):
            assert "COLLATE Latin1_General_100_BIN2_UTF8" in rest   # Delta strings are UTF-8
    assert list(cols) == list(GOLD_TABLES[table])
    for name, spark_type in GOLD_TABLES[table].items():
        want = TSQL_TYPE[kind(spark_type)]
        assert cols[name].startswith(want), (name, cols[name])
        if want == "decimal":
            assert cols[name].startswith("decimal(" + spark_type[8:])
    select = [c.strip() for c in m.group(2).strip().removeprefix("SELECT").split(",")]
    assert select == [f"r.{c}" for c in GOLD_TABLES[table]]


# ------------------------------------------------------------------ Power BI semantic model (TMDL)
TMDL_DIR = ROOT / "src/powerbi/Contoso.SemanticModel/definition"


def parse_table(name):
    text = (TMDL_DIR / "tables" / f"{name}.tmdl").read_text()
    cols = {}
    for m in re.finditer(r"^\tcolumn (\w+)\n\t\tdataType: (\w+)\n\t\tsourceColumn: (\w+)", text, re.M):
        assert m.group(1) == m.group(3)
        cols[m.group(1)] = m.group(2)
    return text, cols


@pytest.mark.parametrize("table", GOLD_TABLES)
def test_tmdl_columns_match_gold_contract(table):
    text, cols = parse_table(table)
    assert cols == {c: TMDL_TYPE[kind(t)] for c, t in GOLD_TABLES[table].items()}
    assert f'Item = "{table}"' in text and 'Schema = "gold"' in text
    assert re.search(rf"^\tpartition {table} = m\n\t\tmode: import", text, re.M)
    assert "\t" in text and "    \tcolumn" not in text          # tabs only for structure


def test_tmdl_model_lists_every_table():
    model = (TMDL_DIR / "model.tmdl").read_text()
    for table in GOLD_TABLES:
        assert f"ref table {table}" in model


@pytest.mark.parametrize("table", GOLD_TABLES)
def test_dax_measures_reference_real_columns(table):
    text, cols = parse_table(table)
    for dax in re.findall(r"^\tmeasure '[^']+' = (.+)$", text, re.M):
        assert dax.count("(") == dax.count(")")
        for t, c in re.findall(r"(\w+)\[(\w+)\]", dax):
            assert t == table and c in cols, dax
    assert re.search(r"^\tmeasure '", text, re.M)


def test_revenue_measure_never_adds_currencies():
    text, _ = parse_table("daily_sales")
    assert "HASONEVALUE(daily_sales[currency])" in text


# ------------------------------------------------------------------ Bicep
BICEP = (ROOT / "infra/main.bicep").read_text()


def test_lifecycle_policy_never_touches_delta_tables():
    rule = BICEP[BICEP.index("managementPolicies"):BICEP.index("resource connector ")]
    prefixes = re.findall(r"prefixMatch: \[(.*?)\]", rule)
    assert prefixes == ["'lake/landing/'"]                   # landing only: not bronze/silver/gold/_delta_log
    assert "tierToArchive" not in rule and "delete:" not in rule


def test_lake_has_no_shared_key_and_no_purview():
    assert "allowSharedKeyAccess: false" in BICEP and "isHnsEnabled: true" in BICEP
    assert "Microsoft.Purview" not in BICEP
    assert "listKeys" not in BICEP and "password" not in BICEP.lower()


@pytest.mark.skipif(not shutil.which("bicep"), reason="bicep CLI not installed")
def test_bicep_builds():
    r = subprocess.run(["bicep", "build", str(ROOT / "infra/main.bicep"), "--stdout"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


# ------------------------------------------------------------------ Databricks files (need a workspace to run)
def test_notebook_imports_exist_and_dbutils_only_in_notebook():
    src = (ROOT / "src/databricks/medallion_job.py").read_text()
    assert src.startswith("# Databricks notebook source")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "lakehouse.medallion":
            for alias in node.names:
                assert hasattr(medallion, alias.name)
    for f in (ROOT / "src/lakehouse").glob("*.py"):
        assert "dbutils" not in f.read_text()                # library stays runnable off Databricks
    assert "input_file_name" not in (ROOT / "src/lakehouse/medallion.py").read_text().replace("not input_file_name()", "")


def test_unity_catalog_sql_targets_real_tables_and_columns():
    sql = (ROOT / "src/databricks/uc_governance.sql").read_text()
    stmts = [s for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()]
    assert len(stmts) == 4
    for s in stmts:
        sqlglot.parse_one(s, read="databricks")
    assert "ROW FILTER lakehouse.gold.region_filter ON (region)" in sql and "region" in GOLD_TABLES["daily_sales"]
    assert "ALTER COLUMN customer_key SET MASK" in sql and "customer_key" in GOLD_TABLES["customer_summary"]
