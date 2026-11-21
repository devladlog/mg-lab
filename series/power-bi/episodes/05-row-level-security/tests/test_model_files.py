"""The TMDL files this episode adds: roles, the hidden mapping table, the UPN domain parameter, no real identities."""
import re
from pathlib import Path

from conftest import ROOT, SRC

DEF = SRC / "ContosoSales.SemanticModel" / "definition"


def test_roles_are_one_file_each_and_read_only():
    roles = sorted(p.name for p in (DEF / "roles").glob("*.tmdl"))
    assert roles == ["Head Office.tmdl", "Store Managers.tmdl"]
    for p in (DEF / "roles").glob("*.tmdl"):
        text = p.read_text()
        assert "\tmodelPermission: read\n" in text
        assert "\tmember " not in text          # members are assigned in the service (Learn), never committed


def test_mapping_table_is_hidden_and_builds_the_upn_from_the_parameter():
    text = (DEF / "tables" / "Store Access.tmdl").read_text()
    assert text.count("isHidden") == 3       # table and both columns
    assert '"@" & UpnDomain' in text
    assert "Text.Lower(" in text             # UPNs compared in lower case (DAX comparison is case-insensitive anyway)


def test_upn_domain_parameter_is_fictional_by_default():
    text = (DEF / "expressions.tmdl").read_text()
    assert re.search(r'expression UpnDomain = "contoso\.com" meta \[IsParameterQuery=true', text)


def test_only_sales_to_customer_filters_both_ways():
    rel = (DEF / "relationships.tmdl").read_text()
    blocks = rel.strip().split("\n\n")
    both = [b.splitlines()[0] for b in blocks if "bothDirections" in b]
    assert both == ["relationship 'Sales to Customer'"]


def test_security_check_measures_exist():
    sales = (DEF / "tables" / "Sales.tmdl").read_text()
    assert "measure 'Who Am I' = USERPRINCIPALNAME()" in sales
    assert "measure 'Visible Stores' = COUNTROWS('Store')" in sales
    assert "measure 'Visible Customers' = COUNTROWS('Customer')" in sales


def test_no_real_tenant_identifiers_anywhere():
    banned = re.compile(r"devladlog|onmicrosoft\.com|momento", re.I)
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in {".tmdl", ".csv", ".json", ".py", ".ps1", ".psm1", ".cs", ".pbip", ".pbir", ".pbism"}:
            if {"schemas", "bin", "obj"} & set(p.parts) or p.name == Path(__file__).name:
                continue
            assert not banned.search(p.read_text(encoding="utf-8", errors="ignore")), p
