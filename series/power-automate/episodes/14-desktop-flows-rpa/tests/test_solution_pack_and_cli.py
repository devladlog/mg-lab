"""pac solution pack, the CLIs, and the Pester suite (real PowerShell, mocked web calls only)."""
import shutil
import subprocess
import sys
import zipfile

import pytest

from conftest import DESKTOP, ROOT, SOLUTION, SRC


@pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
def test_pac_solution_pack(tmp_path):
    out = tmp_path / "PurchaseRpa.zip"
    proc = subprocess.run(["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION),
                           "--packagetype", "Unmanaged"], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = zipfile.ZipFile(out).namelist()
    assert "solution.xml" in names and sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 1


def cli(*args):
    return subprocess.run([sys.executable, "-m", *args], cwd=SRC, capture_output=True, text=True)


def test_padkit_cli():
    c = str(DESKTOP / "enter-purchase-order.contract.json")
    r = cli("padkit", "lint", str(DESKTOP / "enter-purchase-order.robin.txt"), "--contract", c)
    assert r.returncode == 0 and r.stdout.strip() == "OK"
    (wf,) = (SOLUTION / "Workflows").glob("*.json")
    r = cli("padkit", "contract", str(wf), "--contract", c)
    assert r.returncode == 0 and r.stdout.strip() == "OK"


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")
def test_pester_suite():
    cmd = ("Import-Module Pester -MinimumVersion 5.0; "
           f"$r = Invoke-Pester -Path '{ROOT / 'tests' / 'Scripts.Tests.ps1'}' -PassThru -Output None; "
           "Write-Output \"passed=$($r.PassedCount) failed=$($r.FailedCount)\"; "
           "if ($r.FailedCount -gt 0 -or $r.PassedCount -lt 20) { exit 1 }")
    proc = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=900, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
