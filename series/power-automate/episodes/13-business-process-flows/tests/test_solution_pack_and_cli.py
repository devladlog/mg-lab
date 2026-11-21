"""The unpacked solution packs with the Power Platform CLI (no sign-in), the CLI runs, and the Pester suite passes."""
import shutil
import subprocess
import sys
import zipfile

import pytest

from conftest import PROCESS_FILE, ROOT, SAMPLES, SOLUTION, SRC


@pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
def test_pac_solution_pack(tmp_path):
    out = tmp_path / "PurchaseBpf.zip"
    proc = subprocess.run(["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION),
                           "--packagetype", "Unmanaged"], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = zipfile.ZipFile(out).namelist()
    assert "solution.xml" in names and "customizations.xml" in names
    assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 2


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "bpfkit", *args], cwd=SRC, capture_output=True, text=True)


def test_cli_validate_walk_and_payload():
    r = run_cli("validate", str(PROCESS_FILE))
    assert r.returncode == 0 and r.stdout.strip().endswith("OK")
    r = run_cli("walk", str(PROCESS_FILE), "--record", str(SAMPLES / "request-large.json"), "--steps", "next,next,next,next,finish")
    assert r.returncode == 0 and "Finance review" in r.stdout and "Close (Finished)" in r.stdout
    r = run_cli("walk", str(PROCESS_FILE), "--record", str(SAMPLES / "request-incomplete.json"))
    assert r.returncode == 1 and "BLOCKED" in r.stdout and "cts_justification" in r.stdout
    r = run_cli("payload", str(PROCESS_FILE), "--record", str(SAMPLES / "request-large.json"),
                "--stage-ids", str(SAMPLES / "stage-ids.json"), "--steps", "next,abort")
    assert '"statuscode": 3' in r.stdout and "traversedpath" in r.stdout


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")
def test_pester_suite():
    cmd = ("Import-Module Pester -MinimumVersion 5.0; "
           f"$r = Invoke-Pester -Path '{ROOT / 'tests' / 'Set-BpfStage.Tests.ps1'}' -PassThru -Output None; "
           "if ($r.FailedCount -gt 0 -or $r.PassedCount -lt 10) { exit 1 }")
    proc = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr
