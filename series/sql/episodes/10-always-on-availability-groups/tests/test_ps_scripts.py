"""The PowerShell lab-prep scripts: they must parse (PowerShell's own parser) and say what the episode claims. They need
a Windows failover cluster to run (demo.md), so here they are only parsed and read."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS = ROOT / "src" / "ps"
SCRIPTS = sorted(p.name for p in PS.glob("*.ps1"))
pytestmark = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh (PowerShell 7) not installed")


def pwsh(code: str) -> str:
    return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", code], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_parses(name):
    out = pwsh("$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$t,[ref]$e);"
               "$e | ForEach-Object { $_.ToString() }; 'DONE'" % (PS / name))
    assert out.strip() == "DONE", out


def commands(name):
    out = pwsh("$t=$null;$e=$null;$a=[System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$t,[ref]$e);"
               "$a.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true) | "
               "ForEach-Object { $_.GetCommandName() } | ConvertTo-Json -Compress" % (PS / name))
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def test_prepare_builds_the_cluster_in_the_documented_order():
    cmds = [c for c in commands("Prepare-AgCluster.ps1") if c]
    order = ["Install-WindowsFeature", "Test-Cluster", "New-Cluster", "Set-ClusterQuorum", "Enable-SqlAlwaysOn"]
    idx = [cmds.index(c) for c in order]
    assert idx == sorted(idx)
    text = (PS / "Prepare-AgCluster.ps1").read_text(encoding="utf-8")
    assert "-NoStorage" in text and "-StaticAddress" in text and "-FileShareWitness" in text and "-IncludeManagementTools" in text
    assert re.search(r"Enable-SqlAlwaysOn -ServerInstance \$node -Force", text)


def test_remove_undoes_it_in_reverse():
    cmds = [c for c in commands("Remove-AgCluster.ps1") if c]
    assert cmds.index("Disable-SqlAlwaysOn") < cmds.index("Remove-Cluster")
    assert "-CleanupAD" in (PS / "Remove-AgCluster.ps1").read_text(encoding="utf-8")


def test_stop_script_stops_then_starts_the_service():
    cmds = [c for c in commands("Stop-AgPrimary.ps1") if c]
    assert cmds.index("Stop-Service") < cmds.index("Start-Sleep") < cmds.index("Start-Service")


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_script_supports_whatif_and_has_no_secrets(name):
    text = (PS / name).read_text(encoding="utf-8")
    assert "SupportsShouldProcess" in text and "ShouldProcess(" in text
    assert not re.search(r"password|pwd=|secret|token", text, re.IGNORECASE), name
    assert "devladlog" not in text.lower()


def test_the_cluster_name_object_account_and_the_share_path_are_built_correctly():
    out = pwsh("$Domain='CONTOSO';$ClusterName='CON-AGCL01';$WitnessHost='CON-SRV01';$WitnessShare='AgWitness';"
               '$cno = "${Domain}\\${ClusterName}$"; $unc = "\\\\$WitnessHost\\$WitnessShare"; $cno; $unc')
    assert out.split() == ["CONTOSO\\CON-AGCL01$", "\\\\CON-SRV01\\AgWitness"]


def test_the_scripts_default_to_the_lab_names_and_addresses():
    text = (PS / "Prepare-AgCluster.ps1").read_text(encoding="utf-8")
    assert "'CON-SQL01', 'CON-SQL02'" in text and "10.50.0." in text
    ip = re.search(r"\$ClusterIp = '([\d.]+)'", text).group(1)
    assert ip == "10.50.0.44"
