"""The unpacked solution packs into a zip with the Power Platform CLI (no sign-in needed)."""
import shutil
import subprocess
import zipfile

import pytest

from conftest import SOLUTION


@pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")
def test_pac_solution_pack(tmp_path):
    out = tmp_path / "PurchasingReports.zip"
    proc = subprocess.run(
        ["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION), "--packagetype", "Unmanaged"],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = zipfile.ZipFile(out).namelist()
    assert "solution.xml" in names and "customizations.xml" in names
    assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 1
