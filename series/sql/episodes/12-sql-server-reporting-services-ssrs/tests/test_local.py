"""The report's data layer on DuckDB: the procedures' SELECTs, the .rdl's fields and parameters, and expected/ agree."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import rpt_lab as lab  # noqa: E402


@pytest.fixture(scope="module")
def eng():
    e = lab.local_engine()
    yield e
    e.close()


def test_local_run_passes(capsys):
    assert lab.run_local() == 0
    assert "local checks: the report's datasets match" in capsys.readouterr().out


@pytest.mark.parametrize("step", [s for s in lab.STEPS if s.dataset], ids=lambda s: s.key)
def test_each_dataset_matches_expected_and_rdl_fields(eng, step):
    proc = lab.PROC_OF[step.dataset]
    cols, rows = lab.local_query(eng, proc, step.params if step.dataset == "SalesByProduct" else {})
    assert labdb.diff(labdb.read_csv(lab.EXPECTED_DIR / f"{step.key}.csv"), labdb.to_table(cols, rows)) == []
    assert cols == lab.rdl_model()["datasets"][step.dataset]["fields"]


def test_region_filter_is_a_subset_of_all_regions(eng):
    _, all_rows = lab.local_query(eng, lab.PROC_OF["SalesByProduct"], lab.DEFAULTS)
    _, north = lab.local_query(eng, lab.PROC_OF["SalesByProduct"], {**lab.DEFAULTS, "@Region": "North"})
    units = {r[0]: r[1] for r in all_rows}
    assert north and all(r[1] <= units[r[0]] for r in north)


def test_revenue_applies_the_line_discount(eng):
    cols, rows = lab.local_query(eng, lab.PROC_OF["SalesByProduct"], lab.DEFAULTS)
    direct = eng.query("SELECT CAST(SUM(l.Qty * l.UnitPrice * (1 - l.DiscountPct / 100.0)) AS DECIMAL(12,2)) "
                       "FROM Sales.Orders o JOIN Sales.OrderLines l ON l.OrderId = o.OrderId "
                       "WHERE o.OrderDate BETWEEN '2025-03-01' AND '2025-04-30'")[1][0][0]
    assert sum(r[3] for r in rows) == direct


def test_rdl_parameters_match_the_dataset_query_parameters():
    m = lab.rdl_model()
    assert set(m["parameters"]) == {"From", "To", "Region"}
    qp = m["datasets"]["SalesByProduct"]["query_parameters"]
    assert qp == ["@From", "@To", "@Region"]
    assert m["datasets"]["SalesByProduct"]["command"] == "Rpt.usp_SalesByProduct"
    assert m["datasets"]["SalesByProduct"]["command_type"] == "StoredProcedure"
    assert m["datasets"]["Regions"]["command"] == "Rpt.usp_Regions"


def test_rdl_file_is_what_the_generator_writes():
    r = subprocess.run([sys.executable, str(ROOT / "src" / "report" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_rdl_has_no_credentials_or_connection_strings():
    text = lab.RDL.read_text(encoding="utf-8")
    assert not re.search(r"ConnectString|Password|User ID|Integrated Security", text, re.I)
    assert "<DataSourceReference>/MGLab/ContosoBikesRpt</DataSourceReference>" in text
