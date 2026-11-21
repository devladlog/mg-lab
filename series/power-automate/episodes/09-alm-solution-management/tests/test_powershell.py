"""Runs the Pester tests for scripts/Deploy-Solution.ps1 (needs pwsh with Pester)."""
import subprocess

from conftest import ROOT, needs_pwsh


@needs_pwsh
def test_pester_suite_passes():
    cmd = ("$r = Invoke-Pester -Path tests/Deploy-Solution.Tests.ps1 -PassThru -Output None; "
           "Write-Output \"passed=$($r.PassedCount) failed=$($r.FailedCount)\"; exit $r.FailedCount")
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "passed=8 failed=0" in r.stdout


@needs_pwsh
def test_script_parses():
    cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('src/scripts/Deploy-Solution.ps1',[ref]$null,[ref]$e); "
           "exit $e.Count")
    assert subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], cwd=ROOT, timeout=120).returncode == 0
