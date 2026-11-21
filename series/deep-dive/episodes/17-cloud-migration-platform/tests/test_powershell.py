"""The PowerShell collector is tested with Pester and with a round trip into the Python planner.

Both need `pwsh` (PowerShell 7); the Pester run also needs the Pester module (set PESTER_MODULE to its .psd1, or have it installed).
Collecting from a real machine (Get-LocalServerFacts) needs Windows and is not covered here.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) not installed")


def run(*args, timeout=180):
    return subprocess.run([PWSH, "-NoProfile", *args], capture_output=True, text=True, timeout=timeout)


def test_scripts_parse():
    code = ("$e=$null; foreach($f in 'scripts/Inventory.psm1','scripts/Get-ServerInventory.ps1'){"
            "[void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD $f),[ref]$null,[ref]$e); if($e){$e; exit 1}}")
    r = subprocess.run([PWSH, "-NoProfile", "-Command", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_collector_output_feeds_the_planner(tmp_path):
    out = tmp_path / "inv.json"
    r = run("-File", str(ROOT / "scripts" / "Get-ServerInventory.ps1"), "-FromFacts", str(ROOT / "tests" / "fixtures" / "facts.json"),
            "-OutFile", str(out))
    assert r.returncode == 0, r.stderr
    from migplan import inventory, readiness
    inv = inventory.load(out)
    assert [s.name for s in inv.servers] == ["con-app01", "con-old01"]
    findings = readiness.check_inventory(inv)
    assert {f.code for f in findings if f.server == "con-old01"} >= {"os-end-of-support", "sized-as-is"}
    assert not [f for f in findings if f.severity == "blocker"]
    assert any(c.port == 1433 for c in inv.connections)


def test_pester_suite():
    module = os.environ.get("PESTER_MODULE", "Pester")
    r = run("-Command", f"try {{ Import-Module '{module}' -ErrorAction Stop }} catch {{ Write-Output 'Could not load Pester'; exit 2 }}; "
                        f"$r = Invoke-Pester -Path '{ROOT / 'tests' / 'Inventory.Tests.ps1'}' -PassThru -Output None; "
                        "Write-Output \"PESTER passed=$($r.PassedCount) failed=$($r.FailedCount)\"; if ($r.FailedCount -gt 0) { exit 1 }")
    if "Could not load Pester" in r.stdout + r.stderr:
        pytest.skip("Pester module not available")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
