import json
import shutil

import pytest

from pagekit import lint as L
from pagekit.cli import main
from pagekit.siteconfig import load_site
from conftest import BAD, GOOD, ROOT


def codes(findings):
    return sorted((f.code, f.where) for f in findings)


def test_good_site_is_clean_against_portal_json(good_site):
    expected = json.loads((ROOT / "portal.json").read_text())["expected_web_api"]
    assert L.lint(good_site, expected) == []


def test_loader_reads_settings_permissions_roles(good_site):
    assert set(good_site.settings) == {"incident", "contact"}
    assert good_site.settings["incident"].field_list[:2] == ["title", "description"]
    assert good_site.other_settings == {"Authentication/Registration/Enabled": "False"}
    perm = {p.table: p for p in good_site.permissions}
    assert perm["incident"].scope == "contact" and perm["incident"].privileges >= {"read", "create"}
    assert perm["contact"].scope == "self"
    assert good_site.roles["11111111-0000-0000-0000-000000000001"].name == "Store managers"


def test_bad_site_findings(bad_site):
    got = codes(L.lint(bad_site))
    assert ("P001", "Webapi/contact") in got and ("P001", "Webapi/opportunity") in got
    assert ("P002", "Webapi/incident") in got
    assert ("P003", "Webapi/adx_webpage") in got
    assert ("P004", "Webapi/contact") in got
    assert ("P005", "Cases for everyone") in got
    assert ("P006", "Opportunities global read") in got
    assert ("P007", "Webapi/lead") in got
    assert ("P008", "Webapi/accounts") in got
    assert ("P009", "Webapi/annotation") in got


def test_global_anonymous_write_is_error_not_just_warning(bad_site):
    f = [x for x in L.lint(bad_site) if x.where == "Cases for everyone"]
    assert [x.level for x in f] == ["error"]            # P005 replaces the generic P006 for this permission
    assert "public write access" in f[0].message


def test_drift_against_expectation(good_site):
    exp = {"incident": ["title"], "contact": ["firstname", "lastname", "emailaddress1"], "lead": ["fullname"]}
    got = {(f.code, f.where): f for f in L.lint(good_site, exp)}
    assert "extra: createdon" in got[("P012", "Webapi/incident")].message
    assert ("P012", "Webapi/lead") in got


def test_unexpected_enabled_table_warns(good_site):
    got = codes(L.lint(good_site, {"incident": good_site.settings["incident"].field_list}))
    assert got == [("P013", "Webapi/contact")]


def test_use_fields_from_view_replaces_fields_rule(tmp_path):
    site = tmp_path / "s"
    shutil.copytree(GOOD, site)
    (site / "site-settings" / "incident-fields.sitesetting.yml").unlink()
    (site / "site-settings" / "view.sitesetting.yml").write_text(
        "adx_name: Webapi/incident/UseFieldsFromView\nadx_value: 'True'\n")
    got = L.lint(load_site(site))
    assert [(f.code, f.level) for f in got] == [("P010", "info")]


def test_text_scope_and_unknown_role_do_not_crash(tmp_path):
    site = tmp_path / "s"
    (site / "site-settings").mkdir(parents=True)
    (site / "table-permissions").mkdir()
    (site / "site-settings" / "a.sitesetting.yml").write_text("adx_name: Webapi/contact/enabled\nadx_value: 'True'\n")
    (site / "site-settings" / "b.sitesetting.yml").write_text("adx_name: Webapi/contact/fields\nadx_value: 'firstname'\n")
    (site / "table-permissions" / "p.tablepermission.yml").write_text(
        "adx_entitypermissionname: P\nadx_entitylogicalname: contact\nadx_scope: Global\nadx_read: true\n"
        "adx_entitypermission_webrole: [99999999-0000-0000-0000-000000000009]\n")
    assert codes(L.lint(load_site(site))) == [("P006", "P")]


def test_cli_exit_codes_and_output(capsys):
    assert main(["lint", str(GOOD), "--expect", str(ROOT / "portal.json")]) == 0
    assert "0 error(s)" in capsys.readouterr().out
    assert main(["lint", str(BAD)]) == 1
    out = capsys.readouterr().out
    assert "P005" in out and "error(s)" in out
    assert main(["inspect", str(GOOD)]) == 0
    assert "Store manager cases" in capsys.readouterr().out
    assert main(["lint", str(GOOD / "nope")]) == 2


def test_invalid_yaml_is_reported_not_raised(tmp_path, capsys):
    (tmp_path / "site-settings").mkdir()
    (tmp_path / "site-settings" / "x.sitesetting.yml").write_text("adx_value: *\n")
    with pytest.raises(ValueError, match="not valid YAML"):
        load_site(tmp_path)
