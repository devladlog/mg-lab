import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SEC = HERE.parent
sys.path.insert(0, str(SEC))
import vuln_gate as g  # noqa: E402

FIX = HERE / "fixtures"
TODAY = dt.date(2026, 11, 21)
BLOCK = {"CRITICAL", "HIGH"}


def findings():
    return g.load_findings(FIX / "trivy-report-findings.json")


def waiver(vid="CVE-0000-0001", days=30, package=None, owner="alex.demo", reason="no patch in the base image yet"):
    return g.Waiver(vid, package, owner, reason, TODAY + dt.timedelta(days=days))


def test_a_clean_report_passes():
    assert g.load_findings(FIX / "trivy-report-clean.json") == []
    v = g.evaluate([], [], TODAY, BLOCK)
    assert v.passed


def test_critical_and_high_with_a_fix_block_and_the_rest_do_not():
    v = g.evaluate(findings(), [], TODAY, BLOCK)
    assert {f.vuln_id for f in v.blocking} == {"CVE-0000-0001", "CVE-0000-0004"}
    assert {f.vuln_id for f in v.ignored} == {"CVE-0000-0002", "CVE-0000-0003"}  # no fix yet / medium
    assert not v.passed


def test_unfixed_findings_block_when_asked():
    v = g.evaluate(findings(), [], TODAY, BLOCK, only_fixable=False)
    assert "CVE-0000-0002" in {f.vuln_id for f in v.blocking}


def test_a_valid_waiver_lets_one_finding_through_and_is_reported():
    v = g.evaluate(findings(), [waiver("CVE-0000-0001")], TODAY, BLOCK)
    assert {f.vuln_id for f in v.blocking} == {"CVE-0000-0004"}
    assert [(f.vuln_id, w.owner) for f, w in v.waived] == [("CVE-0000-0001", "alex.demo")]


def test_an_expired_waiver_is_no_waiver():
    v = g.evaluate(findings(), [waiver("CVE-0000-0001", days=-1)], TODAY, BLOCK)
    assert "CVE-0000-0001" in {f.vuln_id for f in v.blocking}
    assert [w.vuln_id for w in v.expired] == ["CVE-0000-0001"]


def test_a_waiver_expiring_today_still_counts():
    v = g.evaluate(findings(), [waiver("CVE-0000-0001", days=0)], TODAY, BLOCK)
    assert "CVE-0000-0001" not in {f.vuln_id for f in v.blocking}


def test_a_waiver_for_another_package_does_not_match():
    v = g.evaluate(findings(), [waiver("CVE-0000-0001", package="something-else")], TODAY, BLOCK)
    assert "CVE-0000-0001" in {f.vuln_id for f in v.blocking}
    assert [w.vuln_id for w in v.stale] == ["CVE-0000-0001"]


def test_a_waiver_that_matches_nothing_is_reported_as_stale():
    v = g.evaluate(findings(), [waiver("CVE-1999-9999")], TODAY, BLOCK)
    assert [w.vuln_id for w in v.stale] == ["CVE-1999-9999"]


def test_waiver_file_rules(tmp_path):
    def write(items):
        p = tmp_path / "w.json"
        p.write_text(json.dumps({"waivers": items}))
        return p

    ok = {"id": "CVE-0000-0001", "owner": "alex.demo", "reason": "because", "expires": "2026-12-31"}
    assert len(g.load_waivers(write([ok]), TODAY)) == 1
    for key in ("id", "owner", "reason", "expires"):
        bad = dict(ok); bad[key] = " "
        with pytest.raises(g.InputError, match=key):
            g.load_waivers(write([bad]), TODAY)
    with pytest.raises(g.InputError, match="YYYY-MM-DD"):
        g.load_waivers(write([{**ok, "expires": "next week"}]), TODAY)
    with pytest.raises(g.InputError, match="90 days"):
        g.load_waivers(write([{**ok, "expires": "2027-06-01"}]), TODAY)
    assert g.load_waivers(None, TODAY) == []
    assert g.load_waivers(tmp_path / "missing.json", TODAY) == []


def test_unusable_reports_are_input_errors_not_passes(tmp_path):
    bad = tmp_path / "r.json"
    bad.write_text("not json")
    with pytest.raises(g.InputError):
        g.load_findings(bad)
    bad.write_text(json.dumps({"SchemaVersion": 1}))
    with pytest.raises(g.InputError, match="SchemaVersion 2"):
        g.load_findings(bad)
    bad.write_text(json.dumps({"SchemaVersion": 2, "Results": [{"Target": "t", "Vulnerabilities": [{"VulnerabilityID": "X", "Severity": "SCARY"}]}]}))
    with pytest.raises(g.InputError, match="severity"):
        g.load_findings(bad)


def test_a_report_without_results_means_nothing_found(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"SchemaVersion": 2, "ArtifactName": "x"}))
    assert g.load_findings(p) == []


def test_severity_option_parsing():
    assert g.parse_severities("high, critical") == {"HIGH", "CRITICAL"}
    with pytest.raises(g.InputError):
        g.parse_severities("scary")


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, "-I", str(SEC / "vuln_gate.py"), *args], capture_output=True, text=True, env=env)


def test_cli_exit_codes_and_summary(tmp_path):
    summary = tmp_path / "summary.md"
    env = {"GITHUB_STEP_SUMMARY": str(summary), "PATH": ""}
    clean = run_cli("--report", str(FIX / "trivy-report-clean.json"), "--today", "2026-11-21", env=env)
    assert clean.returncode == 0 and "PASSED" in clean.stdout
    dirty = run_cli("--report", str(FIX / "trivy-report-findings.json"), "--today", "2026-11-21", env=env)
    assert dirty.returncode == 1 and "CVE-0000-0001" in dirty.stdout
    assert "FAILED" in summary.read_text()
    broken = run_cli("--report", str(tmp_path / "nope.json"))
    assert broken.returncode == 2 and "input error" in broken.stderr


def test_the_committed_waiver_file_is_valid_and_empty():
    assert g.load_waivers(SEC / "waivers.json", TODAY) == []
