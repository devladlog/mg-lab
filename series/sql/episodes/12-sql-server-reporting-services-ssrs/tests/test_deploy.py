"""Deploy-Report.ps1: parses (PowerShell's own parser), calls only documented ReportService2010 methods, holds no secret."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "src" / "Deploy-Report.ps1"
TEXT = PS1.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("pwsh"), reason="pwsh not installed")
def test_script_parses_without_errors():
    cmd = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($env:PS1_PATH,[ref]$t,[ref]$e);"
           "$e.Count; $e | % Message")
    out = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                         env={**__import__("os").environ, "PS1_PATH": str(PS1)}).stdout.split()
    assert out[0] == "0", out


def test_only_documented_soap_methods_are_called():
    called = set(re.findall(r"\$Proxy\.(\w+)\(", TEXT) + re.findall(r"\$proxy\.(\w+)\(", TEXT))
    assert called == {"CreateFolder", "CreateDataSource", "CreateCatalogItem", "SetItemDataSources", "DeleteItem"}


def test_paths_match_the_report():
    rdl = (ROOT / "src" / "report" / "SalesByProduct.rdl").read_text(encoding="utf-8")
    assert "/$Folder/ContosoBikesRpt" in TEXT and "<DataSourceReference>/MGLab/ContosoBikesRpt</DataSourceReference>" in rdl
    assert "[string]$Folder       = 'MGLab'" in TEXT


def test_password_comes_from_the_environment_only():
    assert "$env:RS_READER_PASSWORD" in TEXT
    assert not re.search(r"Password\s*=\s*['\"]", TEXT)
    assert "CredentialRetrievalEnum]::Store" in TEXT
