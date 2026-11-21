import base64
import json
import xml.etree.ElementTree as ET

import pytest

from conftest import FIXTURE_FORM, FakeResponse, created, value
from custkit import cli, deploy
from custkit.webapi import DataverseError

SCRIPT = b"var MGL; (function (MGL) { })(MGL || (MGL = {}));\n"
FORM_ID = "00000000-0000-0000-0000-00000000f001"
WR_ID = "00000000-0000-0000-0000-00000000a001"
VIEW_ID = "00000000-0000-0000-0000-00000000b001"
FULL_FORM = FIXTURE_FORM.replace(
    "</rows>\n            </section>",
    '<row><cell id="{00000000-0000-0000-0000-0000000000c9}"><control id="mgl_justification" '
    'classid="{E0DECE4B-6FC8-4a8f-A065-082708572369}" datafieldname="mgl_justification" /></cell></row>'
    "</rows>\n            </section>", 1)


def fresh_environment(stub, form_xml=FULL_FORM):
    """Nothing from episode 3 exists yet: no column, no web resource, no view."""
    stub.on("GET", r"^EntityDefinitions\(LogicalName='mgl_projectrequest'\)/Attributes\(LogicalName='mgl_justification'\)",
            FakeResponse(404, {"error": {"code": "0x80040217", "message": "Could not find attribute"}}))
    stub.on("POST", r"^EntityDefinitions\(LogicalName='mgl_projectrequest'\)/Attributes$",
            created("EntityDefinitions(LogicalName='mgl_projectrequest')/Attributes"))
    stub.on("GET", r"^webresourceset\?", value())
    stub.on("POST", r"^webresourceset$", created("webresourceset", WR_ID))
    stub.on("GET", r"^systemforms\?", value({"formid": FORM_ID, "name": "Information", "formxml": form_xml},
                                            {"formid": "x", "name": "Other form", "formxml": "<form/>"}))
    stub.on("PATCH", r"^systemforms\(", FakeResponse(204))
    stub.on("GET", r"^EntityDefinitions\(LogicalName='mgl_projectrequest'\)\?\$select=ObjectTypeCode",
            FakeResponse(200, {"ObjectTypeCode": 10234}))
    stub.on("GET", r"^savedqueries\?", value())
    stub.on("POST", r"^savedqueries$", created("savedqueries", VIEW_ID))
    stub.on("POST", r"^PublishXml$", FakeResponse(204))
    return stub


def test_first_deploy_creates_everything_in_the_solution_and_publishes(api, stub, cfg):
    fresh_environment(stub)
    lines = []
    rep = deploy.deploy(api, cfg, SCRIPT, out=lines.append)
    assert rep.created == ["column mgl_justification", "web resource mgl_/projectrequest/form.js",
                           "view Open requests over 50,000"]
    assert rep.updated == ["form Information"] and rep.warnings == []
    for method, pattern in (("POST", "Attributes$"), ("POST", "^webresourceset$"), ("PATCH", "^systemforms"),
                            ("POST", "^savedqueries$")):
        (req,) = stub.sent(method, pattern)
        assert req["headers"]["MSCRM.SolutionUniqueName"] == "MGLabDataverse", pattern
    # a new web resource doesn't need publishing; the table (form + view) does
    (pub,) = stub.sent("POST", "^PublishXml$")
    assert pub["json"]["ParameterXml"] == \
        "<importexportxml><entities><entity>mgl_projectrequest</entity></entities></importexportxml>"
    assert "MSCRM.SolutionUniqueName" not in pub["headers"]
    assert lines[-1] == "3 created, 1 updated, 0 unchanged, 0 warning(s)"


def test_form_patch_is_update_only_and_targets_the_named_main_form(api, stub, cfg):
    fresh_environment(stub)
    deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    (patch,) = stub.sent("PATCH", "^systemforms")
    assert patch["url"] == f"systemforms({FORM_ID})" and patch["headers"]["If-Match"] == "*"
    handler = ET.fromstring(patch["json"]["formxml"]).find(".//Handler")
    assert handler.get("functionName") == "MGL.ProjectRequest.onLoad"
    (get_forms,) = stub.sent("GET", "^systemforms")
    assert "objecttypecode eq 'mgl_projectrequest' and type eq 2" in get_forms["url"]


def test_view_uses_the_object_type_code_read_from_metadata(api, stub, cfg):
    fresh_environment(stub)
    deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    (post,) = stub.sent("POST", "^savedqueries$")
    assert 'object="10234"' in post["json"]["layoutxml"]


def test_second_deploy_changes_nothing_and_publishes_nothing(api, stub, cfg):
    fresh_environment(stub)
    deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    patched = stub.sent("PATCH", "^systemforms")[0]["json"]["formxml"]
    view = stub.sent("POST", "^savedqueries$")[0]["json"]
    stub.requests.clear()
    # now everything exists
    stub.on("GET", r"Attributes\(LogicalName='mgl_justification'\)", FakeResponse(200, {"LogicalName": "mgl_justification"}))
    stub.on("GET", r"^webresourceset\?", value({"webresourceid": WR_ID, "content": base64.b64encode(SCRIPT).decode()}))
    stub.on("GET", r"^systemforms\?", value({"formid": FORM_ID, "name": "Information", "formxml": patched}))
    stub.on("GET", r"^savedqueries\?", value({"savedqueryid": VIEW_ID, **view}))
    lines = []
    rep = deploy.deploy(api, cfg, SCRIPT, out=lines.append)
    assert rep.created == [] and rep.updated == [] and len(rep.unchanged) == 4
    assert not [r for r in stub.requests if r["method"] in ("POST", "PATCH")]
    assert "  nothing to publish" in lines


def test_changed_script_is_patched_and_published_by_id(api, stub, cfg):
    fresh_environment(stub)
    stub.on("GET", r"^webresourceset\?", value({"webresourceid": WR_ID, "content": base64.b64encode(b"old").decode()}))
    stub.on("PATCH", r"^webresourceset\(", FakeResponse(204))
    rep = deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    assert "web resource mgl_/projectrequest/form.js" in rep.updated
    (patch,) = stub.sent("PATCH", "^webresourceset")
    assert base64.b64decode(patch["json"]["content"]) == SCRIPT
    assert f"<webresource>{{{WR_ID}}}</webresource>" in stub.sent("POST", "^PublishXml$")[0]["json"]["ParameterXml"]


def test_missing_justification_on_the_form_is_a_warning(api, stub, cfg):
    fresh_environment(stub, form_xml=FIXTURE_FORM)
    rep = deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    assert rep.warnings == ["form Information has no control for mgl_justification: add it in the form designer"]


def test_unknown_form_name_lists_the_main_forms(api, stub, cfg):
    fresh_environment(stub)
    cfg = {**cfg, "form": {**cfg["form"], "name": "Project Request"}}
    with pytest.raises(DataverseError, match="main forms: Information, Other form"):
        deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)


def test_web_resource_filter_quotes_are_escaped(api, stub, cfg):
    fresh_environment(stub)
    cfg = {**cfg, "webresource": {**cfg["webresource"], "name": "mgl_/o'brien.js"}}
    with pytest.raises(ValueError):            # quote isn't a valid name character: refused before any request
        deploy.ensure_webresource(api, cfg, SCRIPT, deploy.DeployReport(), lambda s: None)
    assert not stub.requests


def test_429_is_retried_after_retry_after_seconds(api, stub, cfg):
    waits = []
    api._sleep = waits.append
    calls = {"n": 0}

    def throttled(req):
        calls["n"] += 1
        return FakeResponse(429, {"error": {"message": "throttled"}}, {"Retry-After": "7"}) if calls["n"] == 1 \
            else FakeResponse(200, {"ObjectTypeCode": 10234})
    stub.on("GET", r"ObjectTypeCode", throttled)
    assert deploy.object_type_code(api, "mgl_projectrequest") == 10234 and waits == [7.0]


def test_remove_unregisters_deletes_view_publishes_then_deletes_webresource(api, stub, cfg):
    fresh_environment(stub)
    deploy.deploy(api, cfg, SCRIPT, out=lambda s: None)
    patched = stub.sent("PATCH", "^systemforms")[0]["json"]["formxml"]
    stub.requests.clear()
    stub.on("GET", r"^systemforms\?", value({"formid": FORM_ID, "name": "Information", "formxml": patched}))
    stub.on("GET", r"^savedqueries\?", value({"savedqueryid": VIEW_ID}))
    stub.on("GET", r"^webresourceset\?", value({"webresourceid": WR_ID}))
    stub.on("DELETE", r".", FakeResponse(204))
    deploy.remove(api, cfg, out=lambda s: None)
    order = [(r["method"], r["url"].split("?")[0]) for r in stub.requests if r["method"] != "GET"]
    assert order == [("PATCH", f"systemforms({FORM_ID})"), ("DELETE", f"savedqueries({VIEW_ID})"),
                     ("POST", "PublishXml"), ("DELETE", f"webresourceset({WR_ID})")]
    assert "Handler" not in stub.sent("PATCH", "^systemforms")[0]["json"]["formxml"]


def test_probe_rule_refused_by_server(api, stub, cfg):
    stub.on("PATCH", r"^mgl_projectrequests\(mgl_requestcode='PR-PROBE-120000'\)",
            FakeResponse(400, {"error": {"code": "0x80040265", "message": "Add a business justification."}}))
    lines = []
    assert deploy.probe_rule(api, cfg, 120000, out=lines.append) is True
    (req,) = stub.sent("PATCH")
    assert req["headers"]["If-None-Match"] == "*" and "mgl_justification" not in req["json"]
    assert lines == ["server refused: HTTP 400: Add a business justification."]


def test_probe_rule_accepted_deletes_the_probe_record(api, stub, cfg):
    url = "https://contoso-dev.crm4.dynamics.com/api/data/v9.2/mgl_projectrequests(00000000-0000-0000-0000-0000000000aa)"
    stub.on("PATCH", r"^mgl_projectrequests\(", FakeResponse(204, None, {"OData-EntityId": url}))
    stub.on("DELETE", r"mgl_projectrequests\(", FakeResponse(204))
    assert deploy.probe_rule(api, cfg, 120000, out=lambda s: None) is False
    assert len(stub.sent("DELETE", r"mgl_projectrequests\(00000000")) == 1


def test_render_writes_view_and_patched_form_offline(cfg, tmp_path, capsys):
    from conftest import ROOT
    files = cli.render(cfg, tmp_path, ROOT / "tests" / "fixtures" / "main_form.xml")
    assert sorted(p.name for p in files) == ["main-form.patched.xml", "view.fetchxml.xml", "view.layoutxml.xml"]
    out = capsys.readouterr().out
    assert "form: added OnLoad handler MGL.ProjectRequest.onLoad" in out
    assert "form: ! no control for mgl_justification" in out


def test_config_is_consistent(cfg):
    assert cfg["form"]["onload"].startswith("MGL.ProjectRequest.")
    assert cfg["column"]["logical_name"] == cfg["column"]["schema_name"].lower()
    assert cfg["column"]["logical_name"] in cfg["form"]["required_fields"]
    assert json.dumps(cfg)  # plain JSON, shared with the Node tests
