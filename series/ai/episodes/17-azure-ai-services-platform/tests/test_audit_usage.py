import pytest
from conftest import CS_USER, OWNER, RID, FakePlatform, GOOD_DIAG, assignment, good_account
from aiplatform import audit, usage
from aiplatform.http import Api


def by_id(findings):
    return {f.id: f for f in findings}


def run(account=None, diag=GOOD_DIAG, roles=None):
    return by_id(audit.audit(account or good_account(), diag, roles if roles is not None else [assignment(CS_USER)]))


def test_the_intended_resource_passes_every_rule_except_the_open_network_it_documents():
    f = audit.audit(good_account(), GOOD_DIAG, [assignment(CS_USER)])
    assert [(x.id, x.level) for x in f if x.level != "pass"] == [("network", "warn")]
    assert audit.exit_code(f) == 0
    closed = audit.audit(good_account(properties={"publicNetworkAccess": "Disabled"}), GOOD_DIAG, [assignment(CS_USER)])
    assert all(x.level == "pass" for x in closed)


def test_single_service_kind_is_a_warning_not_a_pass():
    assert run(good_account(kind="TextAnalytics"))["kind"].level == "warn"


def test_keys_enabled_fails_and_says_why():
    f = run(good_account(properties={"disableLocalAuth": False}))["local-auth"]
    assert f.level == "fail" and "every service" in f.detail
    f = run(good_account(properties={"disableLocalAuth": None}))["local-auth"]       # property absent = not disabled
    assert f.level == "fail"


def test_missing_custom_subdomain_fails():
    assert run(good_account(properties={"customSubDomainName": None}))["subdomain"].level == "fail"


@pytest.mark.parametrize("props,level", [({"publicNetworkAccess": "Enabled"}, "warn"), ({"publicNetworkAccess": "Disabled"}, "pass"),
                                         ({"publicNetworkAccess": "Enabled", "networkAcls": {"defaultAction": "Deny"}}, "pass")])
def test_network_rule(props, level):
    assert run(good_account(properties=props))["network"].level == level


def test_diagnostics_rules():
    assert run(diag=[])["diagnostics"].level == "fail"
    only_audit = [{"properties": {"workspaceId": "/w", "logs": [{"category": "Audit", "enabled": True}]}}]
    f = run(diag=only_audit)["diagnostics"]
    assert f.level == "warn" and "RequestResponse" in f.title
    storage_only = [{"properties": {"storageAccountId": "/s", "logs": [{"category": "Audit", "enabled": True}]}}]
    assert run(diag=storage_only)["diagnostics"].level == "fail"          # not Log Analytics
    disabled = [{"properties": {"workspaceId": "/w", "logs": [{"category": "Audit", "enabled": True}, {"category": "RequestResponse", "enabled": False}]}}]
    assert run(diag=disabled)["diagnostics"].level == "warn"
    assert run(diag=None)["diagnostics"].level == "info"


def test_owner_alone_is_not_data_plane_access():
    f = run(roles=[assignment(OWNER, scope=f"/subscriptions/x")])
    assert f["roles"].level == "fail" and "403" in f["roles"].detail
    assert f["roles-mgmt"].level == "info" and "Owner" in f["roles-mgmt"].title


def test_owner_plus_data_role_passes_and_names_the_principal_type():
    f = run(roles=[assignment(OWNER, scope="/subscriptions/x"), assignment(CS_USER, ptype="Group")])
    assert f["roles"].level == "pass" and "Cognitive Services User (Group)" in f["roles"].title


def test_no_data_role_is_only_a_warning_when_keys_still_work():
    f = run(good_account(properties={"disableLocalAuth": False}), roles=[])
    assert f["roles"].level == "warn"


def test_unreadable_documents_are_info_not_a_crash():
    f = by_id(audit.audit(good_account(), None, None))
    assert f["diagnostics"].level == "info" and f["roles"].level == "info"


def test_tags_rule_is_marked_as_our_policy():
    f = run(good_account(tags={"owner": "lab"}))["tags"]
    assert f.level == "warn" and "costcenter" in f.title and f.source == "our policy"


def test_provisioning_state_failed_is_a_fail():
    assert run(good_account(properties={"provisioningState": "Failed"}))["provisioning"].level == "fail"


def test_fetch_reads_three_documents_through_arm(cred):
    t = FakePlatform()
    acc, ds, ra = audit.fetch(Api(cred, transport=t), RID)
    assert acc["kind"] == "AIServices" and len(ds) == 1 and len(ra) == 1
    assert {c["host"] for c in t.calls} == {"management.azure.com"}
    assert any("api-version" in c["query"] and c["query"]["api-version"] == ["2025-06-01"] for c in t.calls)


def test_fetch_degrades_when_diagnostics_and_roles_are_forbidden(cred):
    t = FakePlatform(arm_status={"diagnosticSettings": 403, "roleAssignments": 403})
    acc, ds, ra = audit.fetch(Api(cred, transport=t), RID)
    assert ds is None and ra is None
    assert audit.exit_code(audit.audit(acc, ds, ra)) == 0


def test_fetch_raises_when_the_account_itself_cannot_be_read(cred):
    t = FakePlatform(arm_status={"accounts/contoso-ai": 403})
    with pytest.raises(RuntimeError, match="HTTP 403"):
        audit.fetch(Api(cred, transport=t), RID)


def test_render_summarises_counts():
    text = audit.render(audit.audit(good_account(properties={"disableLocalAuth": False}), GOOD_DIAG, []))
    assert "FAIL  Key authentication enabled" in text and text.splitlines()[-1].endswith("info")


# ---- usage -----------------------------------------------------------------------------------------------------
def test_usage_rolls_up_per_api(cred):
    u = usage.query(Api(cred, transport=FakePlatform()), RID, 30)
    assert u["per_api"]["TotalCalls"] == {"/language/:analyze-text": 4, "TranslateText": 2, "AnalyzeText": 1}
    assert u["per_api"]["TotalErrors"]["/language/:analyze-text"] == 1
    assert u["latency"]["/language/:analyze-text"] == pytest.approx(100.0)       # mean of the per-minute averages 120 and 80
    assert sum(u["billable"]["ProcessedTextRecords"].values()) == 6


def test_usage_request_shape(cred):
    t = FakePlatform()
    usage.query(Api(cred, transport=t), RID, 15)
    q = [c for c in t.calls if c["path"].endswith("/metrics")]
    assert len(q) == 3 and all(c["query"]["api-version"] == ["2019-07-01"] and c["query"]["interval"] == ["PT1M"] for c in q)
    assert q[0]["query"]["metricnames"] == ["TotalCalls,TotalErrors,ClientErrors,ServerErrors"]
    assert q[0]["query"]["$filter"] == ["ApiName eq '*'"] and q[1]["query"]["aggregation"] == ["Average"]
    assert "$filter" not in q[2]["query"]
    start, end = q[0]["query"]["timespan"][0].split("/")
    assert start.endswith("Z") and end.endswith("Z") and start < end


def test_usage_render_has_a_row_per_api_and_billable_units(cred):
    text = usage.render(usage.query(Api(cred, transport=FakePlatform()), RID, 60))
    assert "/language/:analyze-text" in text and "TranslateText" in text
    assert "ProcessedTextRecords: 6" in text and "TextCharactersTranslated: 33" in text


def test_usage_with_no_data_says_metrics_are_delayed():
    assert "delay" in usage.render({"minutes": 5, "per_api": {}, "latency": {}, "billable": {}})


def test_usage_failure_is_explained(cred):
    t = FakePlatform(arm_status={"metrics": 403})
    with pytest.raises(RuntimeError, match="Metrics query failed"):
        usage.query(Api(cred, transport=t), RID)
