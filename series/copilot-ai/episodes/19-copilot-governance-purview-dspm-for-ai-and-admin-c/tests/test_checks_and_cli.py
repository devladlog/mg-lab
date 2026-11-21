import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot_governance.checks import is_copilot_dlp_policy, run_checks  # noqa: E402
from copilot_governance.cli import main  # noqa: E402
from copilot_governance.model import load_snapshot  # noqa: E402
from copilot_governance.oversharing import analyse, classify_permission, load_scan  # noqa: E402

S = ROOT / "src" / "samples"


def by_id(path):
    return {f.id: f for f in run_checks(load_snapshot(path))}


def test_before_snapshot_fails_the_copilot_dlp_check_and_flags_exposed_sites():
    f = by_id(S / "snapshot-before.json")
    assert f["G01"].status == "pass" and f["G02"].status == "pass"
    assert f["G03"].status == "fail" and "G04" not in f
    assert f["G05"].status == "warn"            # EEEU offered in the people picker
    assert f["G06"].status == "warn"            # tenant allows Anyone links
    assert f["G07"].status == "warn" and f["G07"].items == ["https://contoso.example/sites/hr-salaries"]
    assert f["G08"].status == "pass" and len(f["G08"].items) == 1


def test_after_snapshot_has_simulation_dlp_policy_and_is_better():
    f = by_id(S / "snapshot-after.json")
    assert f["G03"].status == "pass"
    assert f["G04"].status == "warn" and "simulation" in f["G04"].detail
    assert f["G05"].status == "pass" and f["G06"].status == "pass" and f["G07"].status == "pass"


def test_missing_sections_are_unknown_not_pass(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"collectedAt": "x", "errors": {"dlpPolicies": "The term 'Get-DlpCompliancePolicy' is not recognized"}}))
    f = by_id(p)
    assert f["G03"].status == "unknown" and "not recognized" in f["G03"].detail
    assert all(x.status == "unknown" for x in f.values())


def test_copilot_policy_detection_by_plane_or_location_id():
    assert is_copilot_dlp_policy({"EnforcementPlanes": ["CopilotExperiences"]})
    assert is_copilot_dlp_policy({"EnforcementPlanes": "CopilotExperiences"})
    assert is_copilot_dlp_policy({"Locations": '[{"Location":"470F2276-E011-4E9D-A6EC-20768BE3A4B0"}]'})
    assert not is_copilot_dlp_policy({"EnforcementPlanes": ["Browser"], "Locations": "[]"})


def test_disabled_label_and_unpublished_label_fail(tmp_path):
    base = json.loads((S / "snapshot-before.json").read_text())
    base["labels"][0]["Disabled"] = True
    base["labels"][1]["Disabled"] = "True"
    p = tmp_path / "a.json"; p.write_text(json.dumps(base))
    assert by_id(p)["G02"].status == "fail"
    base["labels"][1]["Disabled"] = False
    base["labelPolicies"] = []
    p.write_text(json.dumps(base))
    assert by_id(p)["G02"].status == "fail" and "no enabled label policy" in by_id(p)["G02"].detail


def test_audit_off_is_high_failure(tmp_path):
    base = json.loads((S / "snapshot-before.json").read_text())
    base["auditLog"]["UnifiedAuditLogIngestionEnabled"] = False
    p = tmp_path / "a.json"; p.write_text(json.dumps(base))
    assert by_id(p)["G01"].status == "fail"
    assert main([str(p)]) == 1


def test_cli_exit_codes_and_output(capsys):
    assert main([str(S / "snapshot-before.json")]) == 1           # G03 high failure
    out = capsys.readouterr().out
    assert "[FAIL] G03" in out and "New-CopilotLabelDlpPolicy.ps1" in out
    assert main([str(S / "snapshot-after.json")]) == 0
    assert main([str(S / "snapshot-before.json"), "--fail-on", "never"]) == 0


def test_cli_json_with_sharing(capsys):
    assert main([str(S / "snapshot-after.json"), "--json", "--sharing", str(S / "sharing-scan.json")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["sharing"][0] == {"site": "HR Salaries", "scanned": 3, "exposed": 2}


def test_sharing_classification_and_risk():
    assert classify_permission({"link": {"scope": "anonymous", "type": "view"}}) == "anonymous"
    assert classify_permission({"link": {"scope": "existingAccess"}}) == "specific"
    assert classify_permission({"link": {"type": "view"}}) == "link-unknown-scope"
    assert classify_permission({"grantedToV2": {}}) == "direct"
    sites = analyse(load_scan(S / "sharing-scan.json"))
    hr, mkt = sites
    assert len(hr.exposed) == 2 and hr.count("anonymous_links") == 1 and hr.count("org_links") == 2
    risks = {i.path: i.risk for i in hr.exposed}
    assert risks["Documents/salary-bands-2026.xlsx"] == "high"      # anonymous link on a sensitive-looking name
    assert risks["Documents/holiday-calendar.docx"] == "low"
    assert mkt.exposed == []
