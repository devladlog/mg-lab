"""Runs the Pester tests for the two scripts (needs pwsh with Pester 5+) and checks they stay Windows PowerShell 5.1 friendly."""
import re
import subprocess

from conftest import ROOT, SRC, needs_pwsh


@needs_pwsh
def test_pester_suite_passes():
    cmd = ("Import-Module Pester -MinimumVersion 5.0; "
           "$r = Invoke-Pester -Path tests/DlpScripts.Tests.ps1 -PassThru -Output None; "
           "Write-Output \"passed=$($r.PassedCount) failed=$($r.FailedCount)\"; exit $r.FailedCount")
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "passed=11 failed=0" in r.stdout


@needs_pwsh
def test_scripts_parse():
    for name in ("Apply-DlpPolicy.ps1", "Export-DlpPolicy.ps1"):
        cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('src/scripts/{name}',[ref]$null,[ref]$e); "
               "exit $e.Count")
        assert subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], cwd=ROOT, timeout=120).returncode == 0, name


def test_scripts_avoid_syntax_that_windows_powershell_5_1_does_not_have():
    """The admin module needs Windows PowerShell 5.1 (Learn), which has no ??, ?., ?: or pipeline chains."""
    for name in ("Apply-DlpPolicy.ps1", "Export-DlpPolicy.ps1"):
        text = (SRC / "scripts" / name).read_text(encoding="utf-8")
        code = re.sub(r"<#.*?#>", "", text, flags=re.S)
        code = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", "''", code)          # strings out
        assert "??" not in code and "?." not in code and "&&" not in code and "||" not in code, name
        assert not re.search(r"\)\s*\?\s*\S", code), f"{name}: ternary operator"
