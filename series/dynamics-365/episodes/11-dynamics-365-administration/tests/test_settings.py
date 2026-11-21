import pytest

from adminkit import settings
from conftest import FakeResponse, sample


def org_row(**over):
    row = dict(sample("organization.json")["value"][0])
    row.update(over)
    return row


def rules(findings):
    return {f.rule: f.level for f in findings}


def test_sample_environment_is_flagged(cfg):
    assert rules(settings.check(org_row(), cfg)) == {"S001": "error", "S004": "warning", "S005": "info"}


def test_healthy_environment_has_no_errors_or_warnings(cfg):
    ok = org_row(isauditenabled=True, isuseraccessauditenabled=True, auditretentionperiodv2=-1,
                 plugintracelogsetting=1, sessiontimeoutenabled=True)
    assert settings.check(ok, cfg) == []


def test_short_retention_is_a_warning_but_forever_is_fine(cfg):
    base = dict(isauditenabled=True, isuseraccessauditenabled=True, plugintracelogsetting=0, sessiontimeoutenabled=True)
    assert rules(settings.check(org_row(auditretentionperiodv2=30, **base), cfg)) == {"S002": "warning"}
    assert settings.check(org_row(auditretentionperiodv2=-1, **base), cfg) == []
    assert settings.check(org_row(auditretentionperiodv2=90, **base), cfg) == []


def test_policy_can_switch_the_audit_requirement_off(cfg):
    cfg["audit"]["require_enabled"] = False
    assert "S001" not in rules(settings.check(org_row(), cfg))


@pytest.mark.parametrize("days,ok", [(-1, True), (1, True), (365, True), (365000, True), (0, False), (-2, False),
                                     (365001, False)])
def test_retention_validation_follows_learn_range(days, ok):
    if ok:
        assert settings.validate_retention(days) == days
    else:
        with pytest.raises(ValueError):
            settings.validate_retention(days)


def test_describe_labels_retention_and_trace():
    text = "\n".join(settings.describe(org_row(auditretentionperiodv2=-1, plugintracelogsetting=1)))
    assert "retention             forever" in text and "plug-in trace log       Exception" in text


def test_fetch_requires_exactly_one_row(api, stub):
    stub.on("GET", r"^organizations\?", FakeResponse(200, {"value": []}))
    with pytest.raises(ValueError):
        settings.fetch(api)


def test_enable_audit_is_a_dry_run_by_default(api, stub):
    stub.on("GET", r"^organizations\?", FakeResponse(200, {"value": [org_row()]}))
    lines = []
    settings.enable_audit(api, 365, apply=False, out=lines.append)
    assert not stub.sent("PATCH")
    assert any("dry run" in line for line in lines)


def test_enable_audit_patches_update_only_and_reads_back(api, stub):
    state = {"row": org_row()}

    def patch(req):
        state["row"] = {**state["row"], **req["json"]}
        return FakeResponse(204)

    stub.on("GET", r"^organizations\?", lambda req: FakeResponse(200, {"value": [state["row"]]}))
    stub.on("PATCH", r"^organizations\(", patch)
    after = settings.enable_audit(api, 365, apply=True, out=lambda s: None)
    sent = stub.sent("PATCH")[0]
    assert sent["json"] == {"isauditenabled": True, "auditretentionperiodv2": 365}
    assert sent["headers"]["If-Match"] == "*"
    assert after["isauditenabled"] is True


def test_enable_audit_rejects_a_bad_retention_before_any_request(api, stub):
    with pytest.raises(ValueError):
        settings.enable_audit(api, 0, apply=True, out=lambda s: None)
    assert not stub.requests


def test_enable_audit_detects_a_read_back_that_does_not_match(api, stub):
    stub.on("GET", r"^organizations\?", FakeResponse(200, {"value": [org_row()]}))  # never changes
    stub.on("PATCH", r"^organizations\(", FakeResponse(204))
    with pytest.raises(ValueError, match="read-back"):
        settings.enable_audit(api, 365, apply=True, out=lambda s: None)
