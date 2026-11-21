"""The real azure-core pipeline against canned ARM responses: token scope, api-versions, paging, policy states."""
import pytest

from aigov.arm import API, ArmError
from aigov.inventory import Snapshot, collect
from conftest import ACC, RG, RGP, SUB


def test_collect_builds_the_snapshot(arm, fake_arm):
    snap = collect(arm, SUB, RG)
    hr, shadow = snap.accounts
    assert hr.system_id == "hr-bot" and hr.disable_local_auth is True
    assert hr.audit_log_categories == ["Audit", "RequestResponse"]          # disabled Trace is not counted
    (chat,) = hr.deployments
    assert (chat.model, chat.version, chat.sku, chat.upgrade) == ("gpt-5-mini", "2025-08-07", "DataZoneStandard",
                                                                  "NoAutoUpgrade")
    assert {f["name"] for f in chat.rai_filters} == {"Jailbreak", "Indirect Attack"}
    assert shadow.system_id == "" and shadow.audit_log_categories == []
    # policy state resourceId comes back upper-cased; matching is case-insensitive
    assert shadow.non_compliant_policies == ["ai-diagnostic-logs-audit"] and hr.non_compliant_policies == []


def test_requests_use_arm_token_documented_api_versions_and_paging(arm, fake_arm):
    collect(arm, SUB, RG)
    assert set(arm.credential.scopes) == {"https://management.azure.com/.default"}
    assert all(r["headers"]["Authorization"] == "Bearer fake-arm-token" for r in fake_arm.requests)
    by_path = {}
    for r in fake_arm.requests:
        by_path.setdefault(r["path"], []).append(r)
    assert by_path[ACC][0]["query"]["api-version"] == [API["cognitive"]]
    pages = by_path[f"{ACC}/mglab-gov-aoai-abc123/deployments"]
    assert len(pages) == 2 and pages[1]["query"]["$skiptoken"] == ["p2"]          # nextLink followed
    (ps,) = by_path[f"{RGP}/providers/Microsoft.PolicyInsights/policyStates/latest/queryResults"]
    assert ps["method"] == "POST" and ps["query"]["api-version"] == ["2019-10-01"]
    assert ps["query"]["$filter"] == ["complianceState eq 'NonCompliant'"]
    diag = by_path[f"{ACC}/mglab-gov-aoai-abc123/providers/Microsoft.Insights/diagnosticSettings"][0]
    assert diag["query"]["api-version"] == ["2021-05-01-preview"]


def test_default_guardrail_is_not_fetched(arm, fake_arm):
    fake_arm.routes[("GET", f"{ACC}/mglab-gov-aoai-abc123/deployments", None)] = (200, {"value": [
        {"name": "chat", "sku": {"name": "GlobalStandard"},
         "properties": {"model": {"name": "gpt-5-mini", "version": "2025-08-07"}, "raiPolicyName": "Microsoft.DefaultV2"}}]})
    snap = collect(arm, SUB, RG)
    assert snap.accounts[0].deployments[0].rai_filters == []
    assert not any("raiPolicies" in r["path"] for r in fake_arm.requests)


def test_http_errors_surface_with_status(arm, fake_arm):
    fake_arm.routes[("GET", ACC)] = (403, {"error": {"code": "AuthorizationFailed"}})
    with pytest.raises(ArmError) as e:
        collect(arm, SUB, RG)
    assert e.value.status == 403 and "AuthorizationFailed" in str(e.value)


def test_snapshot_round_trip(arm, tmp_path):
    snap = collect(arm, SUB, RG)
    snap.save(tmp_path / "s.json")
    again = Snapshot.load(tmp_path / "s.json")
    assert again == snap
