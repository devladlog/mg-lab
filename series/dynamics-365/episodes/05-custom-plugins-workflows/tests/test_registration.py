import copy

import pytest

from apikit import registration as reg


def test_the_episode_config_passes_every_rule(cfg):
    assert reg.validate(cfg) == []


@pytest.mark.parametrize("change, message", [
    (lambda c: c["custom_api"].update(isprivate=True), "private messages can't be used in plug-ins"),
    (lambda c: c["custom_api"].update(isfunction=True), "only performs actions"),
    (lambda c: c["custom_api"].update(uniquename="new_Assess"), "publisher prefix 'mgl_'"),
    (lambda c: c["custom_api"].update(workflowsdkstepenabled=True,
                                      response_properties=[{"uniquename": "Reasons", "type": "StringArray"}]),
     "can't use Entity, EntityCollection or StringArray: Reasons"),
    (lambda c: c["custom_api"]["request_parameters"].append({"uniquename": "Target", "type": "EntityReference"}),
     "Entity binding creates it"),
    (lambda c: c["steps"][1].update(stage=20), "asynchronous steps can only be registered for PostOperation"),
    (lambda c: c["steps"][0].update(filteringattributes=["mgl_budget"]), "filtering attributes only apply to Update"),
    (lambda c: c["steps"][1].update(filteringattributes=[]), "every update of any column runs the plug-in"),
    (lambda c: c["steps"][1]["filteringattributes"].append("mgl_riskscore"), "filtering on it loops"),
])
def test_learn_rules_are_checked_before_anything_is_sent(cfg, change, message):
    bad = copy.deepcopy(cfg)
    change(bad)
    assert any(message in p for p in reg.validate(bad)), reg.validate(bad)


def test_custom_api_is_one_deep_insert_shaped_like_the_learn_sample(cfg):
    body = reg.custom_api_body(cfg, "00000000-0000-0000-0000-0000000000a1")
    assert body["uniquename"] == body["name"] == "mgl_AssessProjectRequest"
    assert (body["bindingtype"], body["boundentitylogicalname"], body["isfunction"]) == (1, "mgl_projectrequest", False)
    assert body["allowedcustomprocessingsteptype"] == 0
    assert body["PluginTypeId@odata.bind"] == "/plugintypes(00000000-0000-0000-0000-0000000000a1)"
    assert body["CustomAPIRequestParameters"] == []          # Target comes from the Entity binding
    props = {p["uniquename"]: p for p in body["CustomAPIResponseProperties"]}
    assert (props["RiskScore"]["type"], props["RiskLevel"]["type"], props["Reasons"]["type"]) == (7, 10, 10)
    assert props["Reasons"]["name"] == "mgl_AssessProjectRequest.Reasons"   # Learn's naming convention
    assert "isoptional" not in props["RiskScore"]                            # only request parameters have it


def test_diff_unchanged_mutable_immutable_and_new_property(cfg):
    desired = reg.custom_api_body(cfg, "t1")
    existing = copy.deepcopy(desired)
    assert reg.diff_custom_api(existing, desired) == ({}, [], [], [])

    existing["displayname"] = "Old name"
    patch, conflicts, add, extra = reg.diff_custom_api(existing, desired)
    assert patch == {"displayname": "Assess Project Request"} and not conflicts

    existing = copy.deepcopy(desired)
    existing["isfunction"] = True
    existing["CustomAPIResponseProperties"][0]["type"] = 10
    _, conflicts, _, _ = reg.diff_custom_api(existing, desired)
    assert conflicts == ["isfunction: True -> False", "RiskScore.type: 10 -> 7"]

    existing = copy.deepcopy(desired)
    existing["CustomAPIResponseProperties"] = existing["CustomAPIResponseProperties"][:2] + [{"uniquename": "Old", "type": 10}]
    _, conflicts, add, extra = reg.diff_custom_api(existing, desired)
    assert [p["uniquename"] for p in add] == ["Reasons"] and extra == ["Old"] and not conflicts


def test_step_body_and_change_detection(cfg):
    upd = cfg["steps"][1]
    body = reg.step_body(upd, cfg["table"], "t", "m", "f")
    assert body["name"] == "MGLab.D365.Plugins.RiskScoreRefreshPlugin: Update of mgl_projectrequest"
    assert (body["mode"], body["stage"], body["asyncautodelete"], body["supporteddeployment"]) == (1, 40, True, 0)
    assert body["filteringattributes"] == "mgl_budget,mgl_duedate,mgl_justification,mgl_customeraccountid"
    assert body["eventhandler_plugintype@odata.bind"] == "/plugintypes(t)"
    # the server may return the list in another order: not a change
    server = dict(body, filteringattributes="mgl_justification,mgl_budget,mgl_customeraccountid,mgl_duedate")
    assert reg.step_changes(server, body) == {}
    assert reg.step_changes(dict(server, asyncautodelete=False), body) == {"asyncautodelete": True}
    sync = reg.step_body(dict(upd, mode=0, asyncautodelete=True), cfg["table"], "t", "m", "f")
    assert sync["asyncautodelete"] is False                    # only meaningful for async steps
    assert reg.step_body(cfg["steps"][0], cfg["table"], "t", "m", "f")["filteringattributes"] is None


def test_post_image_and_column_and_assembly_bodies(cfg):
    img = reg.post_image_body("s1", ["mgl_riskscore"])
    assert (img["imagetype"], img["entityalias"], img["messagepropertyname"], img["attributes"]) == \
        (1, "PostImage", "Target", "mgl_riskscore")
    col = reg.integer_column(cfg["column"])
    assert col["@odata.type"] == "Microsoft.Dynamics.CRM.IntegerAttributeMetadata"
    assert (col["SchemaName"], col["MinValue"], col["MaxValue"], col["Format"]) == ("mgl_RiskScore", 0, 100, "None")
    asm = reg.assembly_body("MGLab.D365.Plugins", b"MZ\x90\x00")
    assert asm == {"name": "MGLab.D365.Plugins", "content": "TVqQAA==", "isolationmode": 2, "sourcetype": 0}
