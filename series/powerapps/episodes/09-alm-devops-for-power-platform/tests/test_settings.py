"""Resolve-DeploymentSettings.ps1 and the committed settings templates."""
import json
import re
from pathlib import Path

import pytest

from conftest import SETTINGS, SOLUTION, SRC, pwsh

ENV = {
    "TEST_CONNECTION_DATAVERSE": "11111111aaaa4444bbbb222222222222",
    "TEST_CONNECTION_OUTLOOK": "33333333cccc4444dddd555555555555",
    "PROD_CONNECTION_DATAVERSE": "66666666eeee4444ffff777777777777",
    "PROD_CONNECTION_OUTLOOK": "88888888aaaa4444bbbb999999999999",
}


def resolve(template, out, solution=SOLUTION, env=ENV):
    return pwsh("Resolve-DeploymentSettings.ps1", "-Template", template, "-Output", out, "-SolutionPath", solution, env=env)


@pytest.mark.parametrize("target", ["test", "prod"])
def test_templates_resolve_into_the_documented_file_format(tmp_path, target):
    out = tmp_path / f"{target}.json"
    r = resolve(SETTINGS / f"{target}.settings.json", out)
    assert r.code == 0, r
    data = json.loads(out.read_text())
    assert set(data) == {"EnvironmentVariables", "ConnectionReferences"}
    assert data["EnvironmentVariables"] == [{"SchemaName": "contoso_ReminderDomain", "Value": "test.contoso.com" if target == "test" else "contoso.com"}]
    refs = {c["LogicalName"]: c for c in data["ConnectionReferences"]}
    assert refs["contoso_EquipmentDeskOutlook"]["ConnectionId"] == ENV[f"{target.upper()}_CONNECTION_OUTLOOK"]
    assert refs["contoso_EquipmentDeskOutlook"]["ConnectorId"] == "/providers/Microsoft.PowerApps/apis/shared_office365"
    assert set(refs["contoso_EquipmentDeskDataverse"]) == {"LogicalName", "ConnectionId", "ConnectorId"}
    assert "${" not in out.read_text()


def test_the_log_names_the_tokens_but_never_prints_the_values(tmp_path):
    r = resolve(SETTINGS / "test.settings.json", tmp_path / "t.json")
    assert "TEST_CONNECTION_OUTLOOK" in r.out
    for value in ENV.values():
        assert value not in r.out


def test_missing_variables_are_listed_and_nothing_is_written(tmp_path):
    env = {k: v for k, v in ENV.items() if k != "TEST_CONNECTION_OUTLOOK"}
    env["TEST_CONNECTION_OUTLOOK"] = ""
    out = tmp_path / "t.json"
    r = resolve(SETTINGS / "test.settings.json", out, env=env)
    assert r.code == 1
    assert "FAIL no value for: TEST_CONNECTION_OUTLOOK" in r.out
    assert not out.exists()


def test_every_missing_variable_is_named_in_one_message(tmp_path):
    env = {"TEST_CONNECTION_DATAVERSE": "", "TEST_CONNECTION_OUTLOOK": ""}
    r = resolve(SETTINGS / "test.settings.json", tmp_path / "t.json", env=env)
    assert "TEST_CONNECTION_DATAVERSE, TEST_CONNECTION_OUTLOOK" in r.out


def write_template(tmp_path, mutate):
    data = json.loads((SETTINGS / "test.settings.json").read_text())
    mutate(data)
    path = tmp_path / "t.settings.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda d: d["EnvironmentVariables"].clear(), "environment variable contoso_ReminderDomain has no entry"),
        (lambda d: d["EnvironmentVariables"].append({"SchemaName": "contoso_Nope", "Value": "x"}), "contoso_Nope is in the settings but not in the solution"),
        (lambda d: d["EnvironmentVariables"][0].update(Value=" "), "contoso_ReminderDomain has an empty value"),
        (lambda d: d["ConnectionReferences"].pop(), "connection reference contoso_EquipmentDeskOutlook has no entry"),
        (lambda d: d["ConnectionReferences"][0].update(LogicalName="contoso_Typo"), "contoso_Typo is in the settings but not in the solution"),
        (lambda d: d["ConnectionReferences"][0].update(ConnectorId="/providers/Microsoft.PowerApps/apis/shared_sharepointonline"), "connector id differs from the solution's"),
        (lambda d: d["ConnectionReferences"][0].update(ConnectionId=""), "has an empty connection id"),
    ],
)
def test_a_template_that_does_not_match_the_solution_is_refused(tmp_path, mutate, expected):
    template = write_template(tmp_path, mutate)
    out = tmp_path / "out.json"
    r = resolve(template, out)
    assert r.code == 1, r
    assert expected in r.out, r
    assert not out.exists()


def test_invalid_json_is_reported(tmp_path):
    template = tmp_path / "bad.json"
    template.write_text('{ "EnvironmentVariables": [ ')
    r = resolve(template, tmp_path / "o.json")
    assert r.code == 1 and "not valid JSON" in r.out


def test_a_second_environment_variable_in_the_solution_must_be_covered(tmp_path, source_copy):
    extra = source_copy / "environmentvariabledefinitions/contoso_GraceDays"
    extra.mkdir()
    text = (SOLUTION / "environmentvariabledefinitions/contoso_ReminderDomain/environmentvariabledefinition.xml").read_text().replace("contoso_ReminderDomain", "contoso_GraceDays")
    (extra / "environmentvariabledefinition.xml").write_text(text)
    r = resolve(SETTINGS / "test.settings.json", tmp_path / "o.json", solution=source_copy)
    assert r.code == 1 and "environment variable contoso_GraceDays has no entry" in r.out, r


# --- what is committed -----------------------------------------------------------------------

GUID = re.compile(r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}")


@pytest.mark.parametrize("name", ["test", "prod"])
def test_no_connection_id_is_committed_in_a_template(name):
    data = json.loads((SETTINGS / f"{name}.settings.json").read_text())
    for ref in data["ConnectionReferences"]:
        assert re.fullmatch(r"\$\{[A-Z0-9_]+\}", ref["ConnectionId"]), ref


def test_no_guid_or_environment_url_anywhere_in_the_committed_material():
    allowed = {"0ad12346-e108-40b8-a956-9a8f95ea18c9"}  # Learn's Solution checker rule set id
    offenders = []
    for path in SRC.rglob("*"):
        if not path.is_file() or path.suffix not in {".xml", ".json", ".yml", ".yaml", ".ps1", ".md"}:
            continue
        if path.name == "Test-SolutionSource.ps1":
            continue  # it contains the patterns it searches for
        text = path.read_text(encoding="utf-8-sig")
        for m in GUID.findall(text):
            if m.lower() not in allowed:
                offenders.append((path.name, m))
        for pattern in (r"\.crm\d*\.dynamics\.com", r"onmicrosoft\.com", r"devladlog"):
            if re.search(pattern, text):
                offenders.append((path.name, pattern))
    assert offenders == []
