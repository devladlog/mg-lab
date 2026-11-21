"""The unpacked solution packs with the Power Platform CLI (no sign-in), the CLI runs, and the Pester suite passes."""
import json
import shutil
import subprocess
import sys
import zipfile

import pytest

from conftest import ROOT, SAMPLES, SOLUTION, SRC


@pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
def test_pac_solution_pack(tmp_path):
    out = tmp_path / "SalesFollowUp.zip"
    proc = subprocess.run(["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION),
                           "--packagetype", "Unmanaged"], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = zipfile.ZipFile(out).namelist()
    assert "solution.xml" in names and "customizations.xml" in names
    assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 2


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "d365kit", *args], cwd=SRC, capture_output=True, text=True)


def test_cli_check_filter():
    r = run_cli("check-filter", "statecode eq 1", "--row", str(SAMPLES / "opportunity-won.json"))
    assert r.returncode == 0 and "row passes the filter: True" in r.stdout
    r = run_cli("check-filter", "$filter=statecode eq 1")
    assert r.returncode == 1 and "ODATA001" in r.stdout


def test_cli_fires_and_lint_and_bind():
    flow = next((SOLUTION / "Workflows").glob("Wonopportunityfollowup-*[0-9].json"))
    r = run_cli("fires", "--flow", str(flow), "--changed", "statecode,statuscode", "--row", str(SAMPLES / "opportunity-won.json"))
    assert "FIRES" in r.stdout
    r = run_cli("fires", "--flow", str(flow), "--changed", "description", "--row", str(SAMPLES / "opportunity-won.json"))
    assert "does not fire" in r.stdout
    assert run_cli("lint", str(flow)).returncode == 0
    r = run_cli("bind", "opportunities", "00000000-0000-0000-0000-0000000000b1")
    assert r.stdout.strip() == "opportunities(00000000-0000-0000-0000-0000000000b1)"


def test_cli_flowkit_lint_and_run():
    flow = next((SOLUTION / "Workflows").glob("Overdueopportunitiesdigest-*[0-9].json"))
    r = subprocess.run([sys.executable, "-m", "flowkit", "lint", str(flow)], cwd=SRC, capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")
def test_pester_suite():
    cmd = ("Import-Module Pester -MinimumVersion 5.0; "
           f"$r = Invoke-Pester -Path '{ROOT / 'tests' / 'Invoke-DataverseQuery.Tests.ps1'}' -PassThru -Output None; "
           "if ($r.FailedCount -gt 0 -or $r.PassedCount -lt 12) { exit 1 }")
    proc = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr
