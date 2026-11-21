"""PartnerSalesLoad.dtsx cannot be opened here (no SSIS), so these tests check what can go wrong in a hand-built
package: well-formed XML, unique ids, every reference resolving, and the package agreeing with the SQL it talks to.
Whether Visual Studio and SSIS accept it is checked on the first real open (demo.md)."""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "package"))
import build_package as bp  # noqa: E402
import etl_lab as lab  # noqa: E402

DTS = "{www.microsoft.com/SqlServer/Dts}"
TREE = etree.parse(str(lab.DTSX))
ROOT_EL = TREE.getroot()
SQL = lab.sql_text("e01-etl-objects")


def test_file_is_what_the_generator_writes():
    assert subprocess.run([sys.executable, str(ROOT / "src" / "package" / "build_package.py"), "--check"]).returncode == 0


def test_root_is_a_package_with_format_version_8():
    assert ROOT_EL.tag == DTS + "Executable" and ROOT_EL.get(DTS + "ExecutableType") == "Microsoft.Package"
    assert ROOT_EL.get(DTS + "ObjectName") == "PartnerSalesLoad"
    assert [p.text for p in ROOT_EL.findall(DTS + "Property") if p.get(DTS + "Name") == "PackageFormatVersion"] == ["8"]


def test_ids_are_unique():
    dtsids = [e.get(DTS + "DTSID") for e in ROOT_EL.iter() if e.get(DTS + "DTSID")]
    assert len(dtsids) == len(set(dtsids)) and all(re.fullmatch(r"\{[0-9A-F-]{36}\}", d) for d in dtsids)
    refs = [e.get(DTS + "refId") or e.get("refId") for e in ROOT_EL.iter() if (e.get(DTS + "refId") or e.get("refId"))]
    dupes = [r for r, n in Counter(refs).items() if n > 1]
    assert not dupes, dupes


def refs() -> set[str]:
    return {e.get(DTS + "refId") or e.get("refId") for e in ROOT_EL.iter() if (e.get(DTS + "refId") or e.get("refId"))}


def test_connection_manager_references_resolve():
    ids = refs()
    cms = {e.get(DTS + "ObjectName"): e.get(DTS + "DTSID") for e in ROOT_EL.iter(DTS + "ConnectionManager") if e.get(DTS + "refId")}
    assert set(cms) == {"PartnerFile", "ContosoBikesEtl"}
    for c in ROOT_EL.iter("connection"):
        assert c.get("connectionManagerRefId") in ids and c.get("connectionManagerID") == c.get("connectionManagerRefId")
    for t in ROOT_EL.iter("{www.microsoft.com/sqlserver/dts/tasks/sqltask}SqlTaskData"):
        assert t.get("{www.microsoft.com/sqlserver/dts/tasks/sqltask}Connection") == cms["ContosoBikesEtl"]


def test_paths_connect_existing_outputs_to_existing_inputs():
    ids = refs()
    paths = list(ROOT_EL.iter("path"))
    assert len(paths) == 3
    for p in paths:
        assert p.get("startId") in ids and p.get("endId") in ids, p.get("name")
        assert ".Outputs[" in p.get("startId") and ".Inputs[" in p.get("endId")


def test_every_input_column_has_an_upstream_lineage_and_external_column():
    lineage = {c.get("lineageId") for c in ROOT_EL.iter("outputColumn")}
    for c in ROOT_EL.iter("inputColumn"):
        assert c.get("lineageId") in lineage, c.get("refId")
        if c.get("externalMetadataColumnId"):
            assert c.get("externalMetadataColumnId") in refs(), c.get("refId")


def stg_columns() -> list[tuple[str, str]]:
    table = re.search(r"CREATE TABLE Stg\.PartnerSales \((.*?)\n\);", SQL, re.DOTALL).group(1)
    return [(m.group(1), m.group(2)) for m in re.finditer(r"^\s+(\w+)\s+(\w+(?:\(\d+(?:,\d+)?\))?)", table, re.MULTILINE)]


def test_flat_file_columns_match_the_staging_table_in_name_order_and_type():
    ssis_to_sql = {130: "nvarchar", 3: "int", 133: "date", 131: "decimal"}
    ff = [(c.get(DTS + "ObjectName"), int(c.get(DTS + "DataType")), c) for c in ROOT_EL.iter(DTS + "FlatFileColumn")]
    stg = stg_columns()
    assert [n for n, _, _ in ff] == [n for n, _ in stg]
    for (n, t, c), (_, sql_type) in zip(ff, stg):
        assert sql_type.startswith(ssis_to_sql[t]), (n, t, sql_type)
        if t == 130:
            assert sql_type == f"nvarchar({c.get(DTS + 'MaximumWidth')})"
        if t == 131:
            assert sql_type == f"decimal({c.get(DTS + 'DataPrecision')},{c.get(DTS + 'DataScale')})"


def test_destination_tables_exist_and_their_columns_exist():
    for comp in (e for e in ROOT_EL.iter("component") if e.get("componentClassID") == "Microsoft.OLEDBDestination"):
        table = [p.text for p in comp.iter("property") if p.get("name") == "OpenRowset"][0]
        schema, name = re.findall(r"\[(\w+)\]", table)
        block = re.search(rf"CREATE TABLE {schema}\.{name} \((.*?)\n\);", SQL, re.DOTALL).group(1)
        cols = set(re.findall(r"^\s+(\w+)\s", block, re.MULTILINE))
        mapped = {c.get("cachedName") for c in comp.iter("inputColumn")}
        assert mapped <= cols and len(mapped) == 7, (table, mapped - cols)
        assert [p.text for p in comp.iter("property") if p.get("name") == "AccessMode"] == ["3"]   # fast load, table or view


def test_split_rule_uses_only_package_columns_and_is_stored_with_lineage_ids():
    names = {n for n, _ in bp.COLUMNS[:0]} | {c[0] for c in bp.COLUMNS}
    assert set(re.findall(r"[A-Za-z]+", bp.VALID_RULE)) <= names
    stored = [p.text for p in ROOT_EL.iter("property") if p.get("name") == "Expression"][0]
    assert stored.count("#{Package\\Load partner file\\Flat File Source.Outputs[Flat File Source Output].Columns[") == 2
    default_out = [o for o in ROOT_EL.iter("output") if o.get("isDefaultOut") == "true"]
    assert [o.get("name") for o in default_out] == ["Rejected rows"]


def test_control_flow_order_and_parameters():
    ex = [e.get(DTS + "ObjectName") for e in ROOT_EL.find(DTS + "Executables")]
    assert ex == ["Prepare load", "Load partner file", "Merge into Sales.PartnerSales"]
    pcs = [(p.get(DTS + "From"), p.get(DTS + "To")) for p in ROOT_EL.iter(DTS + "PrecedenceConstraint")]
    assert pcs == [("Package\\Prepare load", "Package\\Load partner file"), ("Package\\Load partner file", "Package\\Merge into Sales.PartnerSales")]
    params = {p.get(DTS + "ObjectName"): p.get(DTS + "DataType") for p in ROOT_EL.iter(DTS + "PackageParameter")}
    assert params == {"InputFile": "8", "ServerName": "8"}
    used = set(re.findall(r"@\[\$Package::(\w+)\]", etree.tostring(ROOT_EL, encoding="unicode")))
    assert used == set(params)                       # every parameter is used, and only declared ones are


def test_sql_in_the_package_calls_procedures_that_exist():
    for e in ROOT_EL.iter(DTS + "PropertyExpression"):
        for proc in re.findall(r"EXEC (Etl\.\w+)", e.text or ""):
            assert f"CREATE OR ALTER PROCEDURE {proc}" in SQL
    for t in ROOT_EL.iter("{www.microsoft.com/sqlserver/dts/tasks/sqltask}SqlTaskData"):
        assert t.get("{www.microsoft.com/sqlserver/dts/tasks/sqltask}SqlStatementSource").startswith("EXEC Etl.usp_")


def test_connection_string_uses_driver_19_and_is_built_from_the_server_parameter():
    cs = [e.text for e in ROOT_EL.iter(DTS + "PropertyExpression") if e.get(DTS + "Name") == "ConnectionString" and "Provider" in (e.text or "")][0]
    assert "Provider=MSOLEDBSQL19" in cs and "@[$Package::ServerName]" in cs and "Encrypt=Mandatory" in cs
    assert not re.search(r"(?i)(password|pwd)\s*=", etree.tostring(ROOT_EL, encoding="unicode"))      # Windows authentication only


@pytest.mark.parametrize("name", [lab.FILE1, lab.FILE2])
def test_sample_files_have_the_header_the_package_expects(name):
    assert (ROOT / "data" / name).read_text(encoding="utf-8").splitlines()[0] == ",".join(c[0] for c in bp.COLUMNS)
