"""SalesByProduct.rdl against Microsoft's RDL 2016/01 schema. The XSD is not stored in this repo: save the schema text from
https://learn.microsoft.com/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509 to a file and point
RDL_XSD at it (see README, "Run it locally"). Skipped when RDL_XSD is not set."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
RDL = ROOT / "src" / "report" / "SalesByProduct.rdl"
XSD = os.environ.get("RDL_XSD")
pytestmark = pytest.mark.skipif(not XSD or not Path(XSD).exists(), reason="set RDL_XSD to a copy of the RDL 2016/01 schema")


def schema():
    return etree.XMLSchema(etree.parse(XSD))


def test_report_is_valid_against_the_2016_schema():
    s = schema()
    doc = etree.parse(str(RDL))
    assert s.validate(doc), [str(e) for e in s.error_log][:5]


def test_the_schema_check_really_rejects_a_broken_report():
    s = schema()
    doc = etree.parse(str(RDL))
    ns = {"r": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"}
    ds = doc.getroot().find(".//r:DataSets/r:DataSet/r:Query/r:CommandType", ns)
    ds.tag = "{%s}NotAnElement" % ns["r"]
    assert not s.validate(doc)
