"""Tests for showplan.py (the XML showplan reader) and for the test plans themselves."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import plan_builder as pb  # noqa: E402
import showplan  # noqa: E402

ALL_PLANS = {f"{g}/{k}": x for g, d in (("q01", pb.CUSTOMER_ORDERS), ("q02", pb.OPEN_ORDERS),
                                        ("q03", pb.REVENUE_REPORT)) for k, x in d.items()}


def one(xml):
    plans = showplan.parse_showplan(xml)
    assert len(plans) == 1
    return plans[0]


def test_scan_plan_summary_reads_and_missing_index():
    p = one(pb.CUSTOMER_ORDERS["no index"])
    assert p.is_actual and p.optimization_level == "FULL"
    assert p.access_summary() == "Clustered Index Scan(PK_Orders) + Sort"
    assert p.pages_read == 10420
    scan = p.find("Clustered Index Scan", "pk_orders")[0]             # index names compare case-insensitively
    assert (scan.table, scan.index_kind, scan.actual_rows, scan.actual_executions) == ("Sales.Orders", "Clustered", 7, 1)
    (mi,) = p.missing_indexes
    assert (mi.database, mi.schema, mi.table, mi.impact) == ("ContosoBikesPerf", "Sales", "Orders", 98.9)
    assert mi.equality == ["CustomerId"] and mi.inequality == [] and mi.include == ["OrderDate", "TotalAmount"]


def test_missing_index_ddl_puts_equality_before_inequality():
    mi = one(pb.OPEN_ORDERS["no index"]).missing_indexes[0]
    assert mi.to_create_index() == ("CREATE NONCLUSTERED INDEX [IX_Orders_Status_OrderDate] ON [Sales].[Orders] "
                                    "([Status], [OrderDate]) INCLUDE ([CustomerId], [TotalAmount]);")
    assert mi.to_create_index("IX_Review_Me").startswith("CREATE NONCLUSTERED INDEX [IX_Review_Me]")


def test_key_lookup_is_found_by_name_and_by_lookup_flag():
    p = one(pb.CUSTOMER_ORDERS["narrow index"])
    assert p.access_summary() == "Index Seek(IX_Orders_CustomerId) + Key Lookup(PK_Orders) + Sort"
    assert p.has("Key Lookup") and p.has("Key Lookup", "PK_Orders")
    lookup = p.find("Key Lookup")[0]
    assert lookup.lookup and lookup.actual_executions == 7
    assert p.pages_read == 2 + 21
    # older plans show the lookup as a Clustered Index Seek with Lookup="1": still a Key Lookup
    old_style = pb.plan_xml(pb.Op("Clustered Index Seek", "Clustered Index Seek", 1, table="Orders",
                                  index="PK_Orders", index_kind="Clustered", lookup=True, actual=(7, 7, 21, 0, "Row")))
    assert one(old_style).has("Key Lookup")


def test_columnstore_scan_counts_lob_reads_and_batch_mode():
    p = one(pb.REVENUE_REPORT["columnstore"])
    cs = p.find("Columnstore Index Scan", "NCCI_Orders_Reporting")
    assert cs and cs[0].is_columnstore and cs[0].execution_mode == "Batch"
    assert p.pages_read == 410                       # columnstore segments are LOB reads
    assert p.access_summary() == "Columnstore Index Scan(NCCI_Orders_Reporting)"


def test_parameters_warnings_and_psp_attributes():
    convert = ('<Warnings><PlanAffectingConvert ConvertIssue="Seek Plan" '
               'Expression="CONVERT_IMPLICIT(int,[c].[AccountNumber],0)=(100042)"/></Warnings>')
    xml = pb.plan_xml(pb.scan(), warnings_xml=convert, params=[("@CustomerId", "int", "(4242)", "(1)")], variant=2)
    p = one(xml)
    assert p.parameters == [showplan.Parameter("@CustomerId", "int", "4242", "1")]
    assert p.warnings == ["PlanAffectingConvert Seek Plan: CONVERT_IMPLICIT(int,[c].[AccountNumber],0)=(100042)"]
    assert p.query_variant_id == 2 and not p.has_dispatcher
    assert (p.cpu_ms, p.elapsed_ms) == (12, 15)
    text = showplan.describe(p)
    assert "compiled=4242 runtime=1" in text and "PSP" in text and "Seek Plan" in text


def test_estimated_plan_has_no_runtime_numbers():
    est = pb.plan_xml(pb.Op("Clustered Index Scan", "Clustered Index Scan", 7, table="Orders", index="PK_Orders",
                            index_kind="Clustered"), cpu_ms=None)
    p = one(est)
    assert not p.is_actual and p.pages_read == 0 and p.cpu_ms is None
    assert p.operators[0].actual_rows is None
    assert "n/a (estimated plan)" in showplan.describe(p)


def test_statements_without_a_plan_are_skipped_and_other_xml_is_rejected():
    xml = pb.plan_xml(pb.scan())
    two = xml.replace("</Statements>", '<StmtSimple StatementText="SET NOCOUNT ON" StatementType="SET ON/OFF"/></Statements>')
    assert len(showplan.parse_showplan(two)) == 1
    with pytest.raises(ValueError, match="not a showplan"):
        showplan.parse_showplan("<Something/>")


def test_reads_utf16_sqlplan_files_like_ssms_saves_them(tmp_path, capsys):
    f = tmp_path / "q01.sqlplan"
    f.write_bytes(pb.CUSTOMER_ORDERS["narrow index"].encode("utf-16"))      # BOM + UTF-16 + declaration
    assert showplan.read_plan_file(f).startswith("<?xml")
    assert showplan.main([str(f)]) == 0
    out = capsys.readouterr().out
    assert "access    : Index Seek(IX_Orders_CustomerId) + Key Lookup(PK_Orders) + Sort" in out
    assert "pages read: 23" in out
    g = tmp_path / "utf8.sqlplan"
    g.write_text(re.sub(r"^<\?xml[^>]*\?>", "", pb.CUSTOMER_ORDERS["no index"]), encoding="utf-8")
    assert one(showplan.read_plan_file(g)).pages_read == 10420
    assert showplan.main([]) == 2


def _xsd_path() -> Path | None:
    for p in (os.environ.get("SHOWPLAN_XSD"), ROOT / "tests" / ".xsd" / "showplanxml.xsd"):
        if p and Path(p).exists():
            return Path(p)
    return None


@pytest.mark.skipif(_xsd_path() is None, reason="official showplan XSD not downloaded (see plan_builder.py)")
@pytest.mark.parametrize("name", sorted(ALL_PLANS))
def test_plans_are_schema_valid(name):
    from lxml import etree

    schema = etree.XMLSchema(etree.parse(str(_xsd_path())))
    doc = etree.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", ALL_PLANS[name]).encode("utf-8"))
    assert schema.validate(doc), schema.error_log.last_error
