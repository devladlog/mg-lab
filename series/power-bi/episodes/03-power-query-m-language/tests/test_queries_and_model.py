"""The .pq files, the TMDL model and the Python reference agree with each other."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

import pq_reference as ref

SRC = Path(__file__).resolve().parents[1] / "src"
QUERIES = SRC / "queries"
TABLES = SRC / "ContosoSales.SemanticModel" / "definition" / "tables"


def source_columns(table):
    text = (TABLES / f"{table}.tmdl").read_text(encoding="utf-8")
    return [c.strip('"') for c in re.findall(r"^\t\tsourceColumn: (.+)$", text, flags=re.M)]


def test_tmdl_is_in_sync_with_the_query_files():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "sync_tmdl.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("table", ["Sales", "Date", "Product", "Customer", "Store"])
def test_every_sourceColumn_is_produced_by_the_query(table):
    produced = list(ref.build(SRC / "data" / "exports")[table][0].keys())
    assert sorted(source_columns(table)) == sorted(produced)


def test_query_files_are_the_nine_documented_queries():
    assert sorted(p.stem for p in QUERIES.glob("*.pq")) == sorted(
        ["ExportFolder", "fnReadExport", "fnDimension", "SalesExport",
         "Product", "Customer", "Store", "Date", "Sales"])


def test_staging_query_buffers_before_distinct():
    m = (QUERIES / "SalesExport.pq").read_text()
    assert m.index("Table.Sort(") < m.index("Table.Buffer(") < m.index("Table.Distinct(")


def test_no_hard_coded_path_outside_the_parameter():
    for p in QUERIES.glob("*.pq"):
        if p.stem != "ExportFolder":
            assert not re.search(r'"[A-Za-z]:\\', p.read_text()), p.name
