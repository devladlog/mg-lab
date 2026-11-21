"""Every rule fires on the mistake it is there for: we break a copy of the solution one way at a time."""
import json
import re
from pathlib import Path

import pytest
from conftest import codes

from almkit import checks, load_solution


def flow_path(folder: Path) -> Path:
    return next((folder / "Workflows").glob("AcknowledgeITrequest-*.json"))


def edit_flow(folder: Path, fn):
    p = flow_path(folder)
    data = json.loads(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def edit_text(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def run(folder):
    return checks.check_solution(load_solution(folder))


def test_hard_coded_site_url_in_the_trigger(sol_copy):
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["triggers"]["When_an_IT_request_is_created"]["inputs"]["parameters"].update(
        dataset="https://contoso.sharepoint.com/sites/ITHelpdesk"))
    f = run(sol_copy)
    assert codes(f, "error") == ["A06"] and "SharePoint URL" in f[0].message


def test_hard_coded_mailbox_in_an_action(sol_copy):
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["actions"]["Send_acknowledgement"]["inputs"]["parameters"].update(
        **{"emailMessage/Cc": "servicedesk@contoso.com"}))
    assert codes(run(sol_copy), "error") == ["A06"]


def test_hard_coded_guid_is_flagged_but_the_zero_guids_of_the_samples_are_not(sol_copy):
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["actions"]["Send_acknowledgement"]["inputs"]["parameters"].update(
        listId="5b3c1f2e-9a41-4d0b-8f6e-0c2d7a1b9e33"))
    assert codes(run(sol_copy), "error") == ["A06"]
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["actions"]["Send_acknowledgement"]["inputs"]["parameters"].update(
        listId="00000000-0000-0000-0000-000000000901"))
    assert codes(run(sol_copy), "error") == []


def test_flow_bound_to_a_connection_instead_of_a_reference(sol_copy):
    def bind(d):
        d["properties"]["connectionReferences"]["shared_office365"]["connection"] = {"name": "shared-office365-0000"}
    edit_flow(sol_copy, bind)
    f = run(sol_copy)
    assert "A05" in codes(f, "error")
    assert any("connection reference" in x.message for x in f)


def test_connection_reference_missing_from_customizations(sol_copy):
    edit_text(sol_copy / "Other" / "Customizations.xml", "cts_sharedoffice365_itnotices", "cts_sharedoffice365_other")
    assert "A05" in codes(run(sol_copy), "error")


def test_action_uses_a_connection_the_flow_doesnt_declare(sol_copy):
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["actions"]["Send_acknowledgement"]["inputs"]["host"].update(
        connectionName="shared_teams"))
    assert "A05" in codes(run(sol_copy), "error")


def test_environment_variable_ships_its_current_value(sol_copy):
    (sol_copy / "environmentvariabledefinitions" / "cts_ITSiteUrl" / "environmentvariablevalues.json").write_text("{}")
    f = [x for x in run(sol_copy) if x.code == "A08"]
    assert f and "remove the current value" in f[0].message


def test_unpacked_as_unmanaged_only_cannot_be_packed_as_managed(sol_copy):
    edit_text(sol_copy / "Other" / "Solution.xml", "<Managed>2</Managed>", "<Managed>0</Managed>")
    f = run(sol_copy)
    assert codes(f, "error") == ["A02"] and "--packagetype Both" in f[0].message


def test_flow_not_listed_as_root_component(sol_copy):
    edit_text(sol_copy / "Other" / "Solution.xml", '<RootComponent type="29" id="{00000000-0000-0000-0000-000000000901}" behavior="0" />', "")
    assert codes(run(sol_copy), "error") == ["A04"]


def test_other_publishers_prefix(sol_copy):
    shutil_dir = sol_copy / "environmentvariabledefinitions"
    (shutil_dir / "cts_EnvironmentLabel").rename(shutil_dir / "abc_EnvironmentLabel")
    edit_text(shutil_dir / "abc_EnvironmentLabel" / "environmentvariabledefinition.xml", 'schemaname="cts_EnvironmentLabel"', 'schemaname="abc_EnvironmentLabel"')
    edit_text(sol_copy / "Other" / "Solution.xml", 'schemaName="cts_EnvironmentLabel"', 'schemaName="abc_EnvironmentLabel"')
    assert "A03" in codes(run(sol_copy), "error")


def test_flow_default_differs_from_the_definition(sol_copy):
    def change(d):
        p = d["properties"]["definition"]["parameters"]["IT Requests list (cts_ITRequestsList)"]
        p["defaultValue"] = "Requests"
    edit_flow(sol_copy, change)
    assert codes(run(sol_copy), "error") == ["A07"]


def test_expression_uses_a_parameter_the_flow_doesnt_declare(sol_copy):
    edit_flow(sol_copy, lambda d: d["properties"]["definition"]["actions"]["Send_acknowledgement"]["inputs"]["parameters"].update(
        **{"emailMessage/Cc": "@parameters('Service desk (cts_Nope)')"}))
    f = run(sol_copy)
    assert codes(f, "error") == ["A07"] and "cts_Nope" in f[0].message


def test_unused_environment_variable_is_a_warning(sol_copy):
    # the 1.0.0.0 -> 1.1.0.0 clean-up in reverse: a variable nothing uses any more
    d = sol_copy / "environmentvariabledefinitions" / "cts_StaleDays"
    d.mkdir()
    (d / "environmentvariabledefinition.xml").write_text(
        (sol_copy / "environmentvariabledefinitions" / "cts_ITSiteUrl" / "environmentvariabledefinition.xml")
        .read_text().replace("cts_ITSiteUrl", "cts_StaleDays"))
    edit_text(sol_copy / "Other" / "Solution.xml", "</RootComponents>", '<RootComponent type="380" schemaName="cts_StaleDays" behavior="0" /></RootComponents>')
    f = run(sol_copy)
    assert codes(f, "error") == [] and codes(f, "warning") == ["A09"]


def test_version_must_be_four_numbers(sol_copy):
    edit_text(sol_copy / "Other" / "Solution.xml", "<Version>1.1.0.0</Version>", "<Version>1.1</Version>")
    assert "A01" in codes(run(sol_copy), "error")
