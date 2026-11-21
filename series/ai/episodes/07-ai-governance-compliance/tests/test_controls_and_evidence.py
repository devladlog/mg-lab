from dataclasses import replace
from datetime import date

import pytest

from aigov import controls, evidence, register
from aigov.inventory import Account, Deployment, Snapshot
from conftest import RG, SUB

TODAY = date(2026, 12, 10)
STRICT = [{"name": "Jailbreak", "enabled": True, "blocking": True},
          {"name": "Indirect Attack", "enabled": True, "blocking": True}]


@pytest.fixture
def systems(register_path):
    return register.load(register_path)


def good_account(**over):
    a = Account(id="/x/hr", name="hr", kind="OpenAI", location="swedencentral", system_id="hr-bot",
                disable_local_auth=True, public_network_access="Enabled", audit_log_categories=["Audit"],
                deployments=[Deployment("chat", "gpt-5-mini", "2025-08-07", "DataZoneStandard", "NoAutoUpgrade",
                                        "contoso-hr-strict", STRICT)])
    return replace(a, **over)


def status(findings):
    return {f.control: f.status for f in findings}


def test_compliant_hr_bot_passes_every_control(systems):
    st = status(controls.check_account(systems["hr-bot"], good_account(), TODAY))
    assert set(st) == set(controls.CONTROLS)
    assert all(v == "PASS" for v in st.values()), st


@pytest.mark.parametrize("change, control", [
    (dict(disable_local_auth=False), "SEC-01"),
    (dict(audit_log_categories=["RequestResponse"]), "SEC-02"),
    (dict(non_compliant_policies=["ai-diagnostic-logs-audit"]), "POL-01"),
])
def test_account_level_failures(systems, change, control):
    st = status(controls.check_account(systems["hr-bot"], good_account(**change), TODAY))
    assert st[control] == "FAIL" and sum(v == "FAIL" for v in st.values()) == 1


@pytest.mark.parametrize("dep_change, control", [
    (dict(model="gpt-4.1-nano", version="2025-04-14"), "MOD-01"),
    (dict(version="2025-01-01"), "MOD-01"),                      # right model, unapproved version
    (dict(upgrade="OnceNewDefaultVersionAvailable"), "MOD-02"),
    (dict(sku="GlobalStandard"), "MOD-03"),                       # may process outside the EU data zone
    (dict(rai_policy="Microsoft.DefaultV2", rai_filters=[]), "RAI-01"),
    (dict(rai_filters=STRICT[:1]), "RAI-01"),                     # RAG system without document attack shield
])
def test_deployment_level_failures(systems, dep_change, control):
    acc = good_account()
    acc.deployments = [replace(acc.deployments[0], **dep_change)]
    st = status(controls.check_account(systems["hr-bot"], acc, TODAY))
    assert st[control] == "FAIL", st


def test_embeddings_need_no_guardrail(systems):
    acc = good_account()
    acc.deployments.append(Deployment("embed-small", "text-embedding-3-small", "1", "DataZoneStandard",
                                      "NoAutoUpgrade", "Microsoft.DefaultV2", []))
    assert status(controls.check_account(systems["hr-bot"], acc, TODAY))["RAI-01"] == "PASS"


def test_stale_gate_and_overdue_review_fail(systems):
    hr = systems["hr-bot"]
    st = status(controls.check_account(hr, good_account(), date(2027, 3, 15)))   # gate > 90 days, review passed
    assert st["RAI-02"] == "FAIL" and st["GOV-02"] == "FAIL"
    failed_gate = replace(hr, rai_gate={**hr.rai_gate, "verdict": "FAIL"})
    assert status(controls.check_account(failed_gate, good_account(), TODAY))["RAI-02"] == "FAIL"


def test_low_tier_skips_rai_controls(systems):
    acc = good_account(system_id="helpdesk-triage")
    acc.deployments = [replace(acc.deployments[0], sku="GlobalStandard", rai_policy="Microsoft.DefaultV2")]
    st = status(controls.check_account(systems["helpdesk-triage"], acc, TODAY))
    assert st["MOD-03"] == st["RAI-01"] == st["RAI-02"] == st["RAI-03"] == "N/A"
    assert "FAIL" not in st.values()


def test_evaluate_flags_shadow_ai_and_missing_systems(systems):
    snap = Snapshot("0", "rg", "2026-12-10T10:00:00Z",
                    [good_account(), good_account(name="shadow", id="/x/shadow", system_id=""),
                     good_account(name="typo", id="/x/typo", system_id="hr-b0t")])
    evaluate_ = evidence.evaluate(systems, snap, TODAY)
    results, shadow, not_found = evaluate_
    assert list(results) == ["hr-bot"] and not results["hr-bot"].failed
    assert shadow["shadow"].evidence == "no ai-system-id tag"
    assert "not in register" in shadow["typo"].evidence
    assert not_found == ["ap-agent", "helpdesk-triage"]
    text = evidence.render_console(*evaluate_, snap)
    assert "UNREGISTERED  shadow" in text and text.rstrip().splitlines()[-1].startswith("RESULT: FAIL")


def test_cli_end_to_end_with_live_style_collection(arm, register_path, tmp_path, monkeypatch, capsys):
    """Full CLI path with the fake ARM: snapshot saved, reports written as .txt, exit 1 because of the shadow."""
    import aigov.arm
    import aigov.evidence as ev

    monkeypatch.setattr(aigov.arm, "Arm", lambda cred: arm)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: None)
    code = ev.main(["--register", str(register_path), "--subscription", SUB, "--resource-group", RG,
                    "--save-snapshot", str(tmp_path / "snap.json"), "--out", str(tmp_path / "r"),
                    "--today", "2026-12-10"])
    out = capsys.readouterr().out
    assert code == 1 and "UNREGISTERED  mglab-gov-shadow-abc123: no ai-system-id tag" in out
    report = (tmp_path / "r" / "evidence-hr-bot.txt").read_text()
    assert "**Result: PASS**" in report and "| SEC-01 |" in report and "Alex Demo" in report
    assert (tmp_path / "snap.json").exists() and (tmp_path / "r" / "evidence.json").exists()
    # replaying the snapshot offline gives the same exit code
    assert ev.main(["--register", str(register_path), "--snapshot", str(tmp_path / "snap.json"),
                    "--out", str(tmp_path / "r2"), "--today", "2026-12-10"]) == 1


def test_cli_passes_when_everything_is_registered(arm, fake_arm, register_path, tmp_path, monkeypatch, capsys):
    from conftest import ACC, account

    import aigov.arm
    import aigov.evidence as ev

    fake_arm.routes[("GET", ACC)] = (200, {"value": [account("mglab-gov-aoai-abc123", {"ai-system-id": "hr-bot"})]})
    monkeypatch.setattr(aigov.arm, "Arm", lambda cred: arm)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: None)
    code = ev.main(["--register", str(register_path), "--subscription", SUB, "--resource-group", RG,
                    "--out", str(tmp_path), "--today", "2026-12-10"])
    assert code == 0 and "RESULT: PASS" in capsys.readouterr().out
