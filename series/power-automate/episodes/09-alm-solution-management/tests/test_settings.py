"""Deployment settings: what the committed files must contain, and what happens when something is missing."""
import json
import subprocess
import sys

import pytest
from conftest import DEPLOY, SOLUTION, SRC, RELEASE_1_0, codes

from almkit import checks, load_solution, settings

SOL = load_solution(SOLUTION)
ENV = {"IT_SITE_URL": "https://contoso.sharepoint.com/sites/ITHelpdeskTest", "SERVICEDESK_MAILBOX": "sd-test@contoso.com",
       "CONN_SHAREPOINT": "ef3d1cbb2c3b4e7987e02486584689d3", "CONN_OFFICE365": "4445162937b84457a3465d2f0c2cab7e"}


def load(name):
    return json.loads((DEPLOY / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["settings.test.json", "settings.prod.json"])
def test_committed_templates_match_the_solution(name):
    assert checks.check_settings(SOL, load(name), name, rendered=False) == []


def test_unrendered_template_is_not_accepted_as_a_real_settings_file():
    f = checks.check_settings(SOL, load("settings.test.json"), "t", rendered=True)
    assert codes(f, "error") == ["S03", "S06"]
    assert any("unresolved token" in x.message for x in f)


def test_rendered_file_passes_and_has_no_token_left():
    text = settings.render((DEPLOY / "settings.test.json").read_text(), ENV)
    assert "${" not in text
    assert checks.check_settings(SOL, json.loads(text), "t", rendered=True) == []


def test_environments_differ_only_where_they_should():
    t, p = load("settings.test.json"), load("settings.prod.json")
    diff = [(a["SchemaName"], a["Value"], b["Value"]) for a, b in zip(t["EnvironmentVariables"], p["EnvironmentVariables"]) if a != b]
    assert diff == [("cts_EnvironmentLabel", "TEST", "PROD")]
    assert t["ConnectionReferences"] == p["ConnectionReferences"]  # same tokens, different values in each pipeline group


def test_render_names_every_missing_token_at_once():
    with pytest.raises(settings.SettingsError, match="CONN_OFFICE365, CONN_SHAREPOINT"):
        settings.render((DEPLOY / "settings.test.json").read_text(), {"IT_SITE_URL": "x", "SERVICEDESK_MAILBOX": "y"})


def test_an_empty_variable_counts_as_missing():
    with pytest.raises(settings.SettingsError):
        settings.render("{\"a\": \"${X}\"}", {"X": ""})


def test_a_value_with_a_quote_or_backslash_cannot_break_the_json():
    out = settings.render('{"a": "${X}"}', {"X": 'He said "hi" \\ bye'})
    assert json.loads(out) == {"a": 'He said "hi" \\ bye'}


def test_missing_environment_variable_entry_means_the_default_would_be_used():
    data = load("settings.test.json")
    data["EnvironmentVariables"] = [e for e in data["EnvironmentVariables"] if e["SchemaName"] != "cts_ITSiteUrl"]
    f = checks.check_settings(SOL, data, "t", rendered=False)
    assert codes(f, "error") == ["S02"] and "contoso.sharepoint.com/sites/ITHelpdesk" in f[0].message


def test_missing_connection_reference_entry():
    data = load("settings.test.json")
    data["ConnectionReferences"] = data["ConnectionReferences"][:1]
    assert codes(checks.check_settings(SOL, data, "t", rendered=False), "error") == ["S04"]


def test_settings_from_the_previous_release_name_a_variable_that_is_gone():
    data = load("settings.test.json")
    data["EnvironmentVariables"].append({"SchemaName": "cts_StaleDays", "Value": "7"})
    f = checks.check_settings(SOL, data, "t", rendered=False)
    assert codes(f, "error") == ["S02"] and "isn't an environment variable" in f[0].message
    # and against the release that still has it, the same file is fine
    assert checks.check_settings(load_solution(RELEASE_1_0), data, "t", rendered=False) == []


def test_new_release_needs_entries_for_new_variables():
    """The 1.0.0.0 release has cts_StaleDays; the committed 1.1.0.0 settings don't know it: that is why the file moves with the solution."""
    f = checks.check_settings(load_solution(RELEASE_1_0), load("settings.test.json"), "t", rendered=False)
    assert codes(f, "error") == ["S02"] and "cts_StaleDays" in f[0].message


def test_wrong_connector_and_odd_connection_ids():
    data = load("settings.test.json")
    data["ConnectionReferences"][0]["ConnectorId"] = "/providers/Microsoft.PowerApps/apis/shared_teams"
    data["ConnectionReferences"][1]["ConnectionId"] = "not-an-id"
    assert codes(checks.check_settings(SOL, data, "t", rendered=False), "error") == ["S05", "S06"]


def test_empty_connection_id_like_create_settings_writes_it():
    data = load("settings.test.json")
    data["ConnectionReferences"][0]["ConnectionId"] = ""
    f = checks.check_settings(SOL, data, "t", rendered=False)
    assert codes(f, "error") == ["S06"] and "empty" in f[0].message


def test_empty_value_is_a_warning():
    data = load("settings.test.json")
    data["EnvironmentVariables"][0]["Value"] = ""
    assert codes(checks.check_settings(SOL, data, "t", rendered=False), "warning") == ["S03"]


def test_cli_exit_codes(tmp_path):
    import os
    base = {**os.environ, "PYTHONPATH": str(SRC)}
    base.pop("IT_SITE_URL", None)
    run = lambda *a, env=None: subprocess.run([sys.executable, "-m", "almkit", *a], capture_output=True, text=True,
                                              env={**base, **(env or {})}, cwd=SRC)
    out = tmp_path / "s.json"
    r = run("render-settings", str(DEPLOY / "settings.test.json"), "--solution", str(SOLUTION), "--out", str(out), env=ENV)
    assert r.returncode == 0 and out.exists(), r.stdout + r.stderr
    out.unlink()
    r = run("render-settings", str(DEPLOY / "settings.test.json"), "--solution", str(SOLUTION), "--out", str(out))
    assert r.returncode == 2 and "no value for" in r.stdout and not out.exists()
    r = run("check", str(SOLUTION), "--previous", str(RELEASE_1_0), "--templates", str(DEPLOY / "settings.test.json"))
    assert r.returncode == 0 and "0 error(s)" in r.stdout
    r = run("check", str(SOLUTION), "--settings", str(DEPLOY / "settings.test.json"))
    assert r.returncode == 1
