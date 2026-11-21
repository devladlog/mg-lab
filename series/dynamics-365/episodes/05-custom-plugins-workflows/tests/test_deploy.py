import copy

import pytest

from apikit import deploy, registration
from apikit.webapi import DataverseError

DLL = b"MZ fake assembly bytes v1"


def run(reg_api, cfg, dll=DLL):
    lines = []
    rep = deploy.deploy(reg_api, cfg, dll, out=lines.append)
    return rep, lines


def test_first_deploy_creates_everything_in_order_inside_the_solution(reg_api, registry, cfg):
    rep, lines = run(reg_api, cfg)
    assert rep.summary() == "9 created, 0 updated, 0 unchanged"
    posts = [r["url"].split("?")[0] for r in registry.requests if r["method"] == "POST"]
    assert posts == ["EntityDefinitions(LogicalName='mgl_projectrequest')/Attributes", "pluginassemblies",
                     "plugintypes", "plugintypes", "customapis", "sdkmessageprocessingsteps",
                     "sdkmessageprocessingstepimages", "sdkmessageprocessingsteps", "sdkmessageprocessingstepimages"]
    assert all(r["headers"].get("MSCRM.SolutionUniqueName") == "MGLabDataverse"
               for r in registry.requests if r["method"] == "POST")
    # the custom API points at the main-operation type, the steps at the async type
    types = {t["typename"]: t["plugintypeid"] for t in registry.rows["plugintypes"]}
    (api_row,) = registry.rows["customapis"]
    assert api_row["PluginTypeId@odata.bind"] == f"/plugintypes({types['MGLab.D365.Plugins.AssessProjectRequestApi']})"
    for step in registry.rows["sdkmessageprocessingsteps"]:
        assert step["eventhandler_plugintype@odata.bind"].endswith(f"({types['MGLab.D365.Plugins.RiskScoreRefreshPlugin']})")
    assert lines[-1] == rep.summary()


def test_second_deploy_changes_nothing(reg_api, registry, cfg):
    run(reg_api, cfg)
    before = len(registry.requests)
    rep, _ = run(reg_api, cfg)
    assert rep.summary() == "0 created, 0 updated, 9 unchanged"
    assert [r for r in registry.requests[before:] if r["method"] != "GET"] == []


def test_new_dll_updates_only_the_assembly_content(reg_api, registry, cfg):
    run(reg_api, cfg)
    rep, lines = run(reg_api, cfg, dll=b"MZ fake assembly bytes v2")
    assert rep.updated == ["assembly MGLab.D365.Plugins"] and not rep.created
    (patch,) = registry.sent("PATCH")
    assert patch["url"].startswith("pluginassemblies(") and set(patch["json"]) == {"content"}
    assert patch["headers"]["If-Match"] == "*"


def test_major_or_minor_version_change_is_refused(reg_api, registry, cfg):
    run(reg_api, cfg)
    registry.rows["pluginassemblies"][0]["version"] = "1.0.0.0"
    newer = copy.deepcopy(cfg)
    newer["assembly"]["version"] = "2.0.0.0"
    with pytest.raises(DataverseError, match="different assembly"):
        deploy.deploy(reg_api, newer, b"MZ v2", out=lambda s: None)


def test_immutable_custom_api_change_is_refused_not_ignored(reg_api, registry, cfg):
    run(reg_api, cfg)
    changed = copy.deepcopy(cfg)
    changed["custom_api"]["allowedcustomprocessingsteptype"] = 2
    with pytest.raises(DataverseError, match="allowedcustomprocessingsteptype: 0 -> 2.*Delete the custom API"):
        deploy.deploy(reg_api, changed, DLL, out=lambda s: None)


def test_new_response_property_is_added_with_its_own_create(reg_api, registry, cfg):
    run(reg_api, cfg)
    more = copy.deepcopy(cfg)
    more["custom_api"]["response_properties"].append({"uniquename": "ScoredOn", "type": "DateTime"})
    rep, lines = run(reg_api, more)
    (post,) = registry.sent("POST", "^customapiresponseproperties")
    assert post["json"]["type"] == 1 and post["json"]["CustomAPIId@odata.bind"].startswith("/customapis(")
    assert rep.updated == ["custom API mgl_AssessProjectRequest"]


def test_changed_filtering_attributes_patch_the_step(reg_api, registry, cfg):
    run(reg_api, cfg)
    fewer = copy.deepcopy(cfg)
    fewer["steps"][1]["filteringattributes"] = ["mgl_budget"]
    rep, lines = run(reg_api, fewer)
    (patch,) = registry.sent("PATCH", "^sdkmessageprocessingsteps")
    assert patch["json"] == {"filteringattributes": "mgl_budget"}
    assert "~ step Update (PostOperation, Asynchronous): filteringattributes" in lines


def test_invalid_config_sends_nothing(reg_api, registry, cfg):
    bad = copy.deepcopy(cfg)
    bad["custom_api"]["isprivate"] = True
    with pytest.raises(registration.ConfigError):
        deploy.deploy(reg_api, bad, DLL)
    assert registry.requests == []


def test_remove_deletes_in_reverse_order_and_keeps_the_column(reg_api, registry, cfg):
    run(reg_api, cfg)
    lines = []
    assert deploy.remove(reg_api, cfg, out=lines.append) == 6
    deletes = [r["url"].split("(")[0] for r in registry.sent("DELETE")]
    assert deletes == ["sdkmessageprocessingsteps"] * 2 + ["customapis", "plugintypes", "plugintypes", "pluginassemblies"]
    assert lines[-1] == "6 removed (column mgl_riskscore kept)"
    assert "mgl_riskscore" in registry.columns
