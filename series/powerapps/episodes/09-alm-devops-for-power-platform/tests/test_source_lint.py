"""Test-SolutionSource.ps1: passes on the real source, and every rule fails when it should."""
import re

import pytest

from conftest import SOLUTION, pwsh

SOLUTION_XML = "Other/Solution.xml"


def edit(path, old, new):
    text = path.read_text(encoding="utf-8-sig")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8-sig")


def lint(folder):
    return pwsh("Test-SolutionSource.ps1", "-Path", folder)


def test_the_committed_source_passes_every_rule():
    r = lint(SOLUTION)
    assert r.code == 0, r
    assert "passed all checks" in r.out


@pytest.mark.parametrize(
    "rule, mutate",
    [
        ("S02", lambda d: edit(d / SOLUTION_XML, "<UniqueName>EquipmentDesk</UniqueName>", "<UniqueName>OtherThing</UniqueName>")),
        ("S03", lambda d: edit(d / SOLUTION_XML, "<Version>1.0.0.0</Version>", "<Version>1.0</Version>")),
        ("S04", lambda d: edit(d / SOLUTION_XML, "<Managed>2</Managed>", "<Managed>0</Managed>")),
        ("S05", lambda d: edit(d / SOLUTION_XML, "<CustomizationPrefix>contoso</CustomizationPrefix>", "<CustomizationPrefix>fabrikam</CustomizationPrefix>")),
        ("S06", lambda d: edit(d / SOLUTION_XML, "<RootComponents />", '<RootComponents><RootComponent type="380" schemaName="contoso_Ghost" behavior="0" /></RootComponents>')),
        ("S07", lambda d: edit(d / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml", 'schemaname="contoso_ReminderDomain"', 'schemaname="other_ReminderDomain"')),
        ("S08", lambda d: (d / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariablevalues.json").write_text("{}")),
        ("S09", lambda d: edit(d / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml", "<type>100000000</type>", "<type>100000005</type>")),
        ("S10", lambda d: edit(d / "Other/Customizations.xml", "<iscustomizable>1</iscustomizable>", "<connectionid>abc</connectionid><iscustomizable>1</iscustomizable>")),
        ("S10", lambda d: edit(d / "Other/Customizations.xml", "/providers/Microsoft.PowerApps/apis/shared_office365", "shared_office365")),
        ("S11", lambda d: edit(d / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml", "<defaultvalue>contoso.com</defaultvalue>", "<defaultvalue>https://org1a2b3c.crm4.dynamics.com</defaultvalue>")),
        ("S11", lambda d: edit(d / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml", "<defaultvalue>contoso.com</defaultvalue>", "<defaultvalue>labtenant.onmicrosoft.com</defaultvalue>")),
    ],
)
def test_each_rule_fails_when_its_mistake_is_made(source_copy, rule, mutate):
    mutate(source_copy)
    r = lint(source_copy)
    assert r.code == 1, r
    assert re.search(rf"^FAIL {rule} ", r.out, re.M), r


def test_a_missing_customizations_file_is_reported_not_a_crash(source_copy):
    (source_copy / "Other/Customizations.xml").unlink()
    r = lint(source_copy)
    assert r.code == 1 and "FAIL S01" in r.out, r


def test_broken_xml_is_reported(source_copy):
    (source_copy / SOLUTION_XML).write_text("<ImportExportXml><oops></ImportExportXml>")
    r = lint(source_copy)
    assert r.code == 1 and "FAIL S01" in r.out, r


def test_several_mistakes_are_all_listed_in_one_run(source_copy):
    edit(source_copy / SOLUTION_XML, "<Version>1.0.0.0</Version>", "<Version>one</Version>")
    edit(source_copy / SOLUTION_XML, "<Managed>2</Managed>", "<Managed>1</Managed>")
    r = lint(source_copy)
    assert "FAIL S03" in r.out and "FAIL S04" in r.out, r


def test_a_folder_that_is_a_dependency_and_not_a_root_component_is_fine(source_copy):
    # real exports list environment variables as dependencies; only a dangling root component is an error
    r = lint(source_copy)
    assert r.code == 0, r
    assert "<RootComponents />" in (source_copy / SOLUTION_XML).read_text(encoding="utf-8-sig")
