import re
import shutil

import pytest
from lxml import etree

import build_rdl
import rdl_lint
from conftest import ROOT, SRC

RDL = SRC / "report" / "ContosoStoreStatement.rdl"
XSD = ROOT / "tests" / "schemas" / "reportdefinition-2016-01.xsd"
NS = {"r": build_rdl.NS}


def test_committed_rdl_is_up_to_date():
    assert RDL.read_text(encoding="utf-8") == build_rdl.pretty(build_rdl.build())


def test_rdl_is_valid_against_microsofts_schema():
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    doc = etree.parse(str(RDL))
    assert schema.validate(doc), schema.error_log


def test_lint_is_clean():
    assert rdl_lint.lint(RDL) == []


def test_dax_in_the_report_is_the_dax_file():
    doc = etree.parse(str(RDL))
    text = doc.xpath("//r:CommandText/text()", namespaces=NS)[0]
    body = "\n".join(l for l in (SRC / "dax" / "store-statement.dax").read_text(encoding="utf-8").splitlines() if not l.startswith("//")).strip()
    assert text == body
    assert "@Year" in text and "'Date'[Year] = @Year" in text


def test_design_facts():
    doc = etree.parse(str(RDL))
    assert doc.xpath("//r:Page/r:PageWidth/text()", namespaces=NS) == ["8.27in"]
    assert doc.xpath("//r:ReportSection/r:Width/text()", namespaces=NS) == ["6.5in"]
    assert doc.xpath("//r:Group[@Name='Store']/r:PageBreak/r:BreakLocation/text()", namespaces=NS) == ["Between"]
    assert len(doc.xpath("//r:TablixMember[r:RepeatOnNewPage='true'][r:KeepWithGroup='After']", namespaces=NS)) == 2
    assert doc.xpath("//r:ConnectString/text()", namespaces=NS)[0] == "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Contoso Sales (Lab);Initial Catalog=ContosoSales"


def test_no_guid_secret_or_real_name_in_the_rdl():
    t = RDL.read_text(encoding="utf-8")
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", t)
    assert not re.search(r"password|pwd=|secret|devladlog", t, re.I)


def mutate(tmp_path, old, new):
    p = tmp_path / "bad.rdl"
    t = RDL.read_text(encoding="utf-8")
    assert old in t, old
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    return rdl_lint.lint(p)


def codes(res):
    return {c for c, _, _ in res}


def test_wide_body_is_a_blank_page_error(tmp_path):
    t = RDL.read_text(encoding="utf-8")
    p = tmp_path / "wide.rdl"
    p.write_text(re.sub(r"(</Body>\s*<Width>)6\.5in", r"\g<1>7.2in", t), encoding="utf-8")
    res = rdl_lint.lint(p)
    assert "RL001" in codes(res) and any("wider than the page" in m for _, _, m in res)


def test_header_that_does_not_repeat_is_a_warning(tmp_path):
    t = RDL.read_text(encoding="utf-8").replace("<RepeatOnNewPage>true</RepeatOnNewPage>", "")
    p = tmp_path / "norepeat.rdl"
    p.write_text(t, encoding="utf-8")
    assert "RL002" in codes(rdl_lint.lint(p))


def test_unbound_query_parameter_is_an_error(tmp_path):
    res = mutate(tmp_path, "<QueryParameter Name=\"@Year\">", "<QueryParameter Name=\"@Other\">")
    assert "RL003" in codes(res)


def test_parameter_bound_to_a_missing_report_parameter(tmp_path):
    res = mutate(tmp_path, "<Value>=Parameters!Year.Value</Value>", "<Value>=Parameters!Nope.Value</Value>")
    assert any(c == "RL003" and "existing report parameter" in m for c, _, m in res)


def test_credentials_or_guid_in_the_connection_string(tmp_path):
    assert "RL004" in codes(mutate(tmp_path, "Initial Catalog=ContosoSales", "Initial Catalog=ContosoSales;Password=x"))
    assert "RL004" in codes(mutate(tmp_path, "Initial Catalog=ContosoSales", "Initial Catalog=00000000-0000-0000-0000-000000000001"))


def test_missing_page_number_and_unknown_field(tmp_path):
    assert "RL005" in codes(mutate(tmp_path, "Globals!PageNumber", "Globals!ReportName"))
    assert "RL006" in codes(mutate(tmp_path, "=Fields!Units.Value", "=Fields!Unitz.Value"))


def test_schema_violation_is_reported(tmp_path):
    assert codes(mutate(tmp_path, "<Language>en-US</Language>", "<Language>en-US</Language><Bogus/>")) == {"RL000"}


def test_a_size_without_a_proper_unit_is_an_error(tmp_path):
    res = mutate(tmp_path, "<PageWidth>8.27in</PageWidth>", "<PageWidth>8.27inin</PageWidth>")
    assert "RL008" in codes(res)
