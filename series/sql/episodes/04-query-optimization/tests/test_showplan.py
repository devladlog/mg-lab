"""Tests for showplan.py (same file as episode 3): the parts episode 4 relies on."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import plan_builder as pb  # noqa: E402
import showplan  # noqa: E402


def one(xml):
    (plan,) = showplan.parse_showplan(xml)
    return plan


def test_compiled_and_runtime_parameter_values():
    p = one(pb.SNIFFING["then Megastore"])
    assert p.parameters == [showplan.Parameter("@CustomerId", "int", "4242", "1")]
    lookup = p.find("Key Lookup")[0]
    assert (lookup.actual_executions, lookup.actual_rows) == (60000, 60000)
    assert p.pages_read == 180152
    assert "compiled=4242 runtime=1" in showplan.describe(p)


def test_plan_affecting_convert_warning():
    p = one(pb.CONVERSION["int literal"])
    assert p.warnings == ["PlanAffectingConvert Seek Plan: "
                          "CONVERT_IMPLICIT(int,[ContosoBikesPerf].[Sales].[Customers].[AccountNumber],0)=[@1]"]
    assert p.find("Index Scan", "UX_Customers_AccountNumber")[0].table == "Sales.Customers"
    assert one(pb.CONVERSION["varchar literal"]).warnings == []


def test_operator_level_warnings_are_collected():
    spill = pb.Op("Sort", "Sort", 7, [pb.scan()], actual=(7, 1, 0, 0, "Row"),
                  warnings_xml='<Warnings><SpillToTempDb SpillLevel="1"/></Warnings>')
    p = one(pb.plan_xml(spill))
    assert p.find("Sort")[0].warnings == ["SpillToTempDb"]
    assert "warning   : SpillToTempDb" in showplan.describe(p)


def test_psp_query_variant_and_dispatcher_are_reported():
    p = one(pb.plan_xml(pb.scan(), variant=3))
    assert p.query_variant_id == 3 and not p.has_dispatcher


def test_sqlplan_file_in_utf16(tmp_path, capsys):
    f = tmp_path / "sniffing-4.sqlplan"
    f.write_bytes(pb.SNIFFING["4242 first"].encode("utf-16"))
    assert showplan.main([str(f)]) == 0
    assert "Index Seek(IX_Orders_CustomerId) + Key Lookup(PK_Orders) + Sort" in capsys.readouterr().out


def test_rejects_documents_that_are_not_showplans():
    with pytest.raises(ValueError):
        showplan.parse_showplan("<ShowPlan/>")
