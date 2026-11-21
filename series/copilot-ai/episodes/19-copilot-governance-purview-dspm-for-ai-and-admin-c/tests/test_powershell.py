import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from copilot_governance.checks import run_checks  # noqa: E402
from copilot_governance.model import load_snapshot  # noqa: E402

SNAP = ROOT / "src" / "scripts" / "Export-CopilotGovernanceSnapshot.ps1"
DLP = ROOT / "src" / "scripts" / "New-CopilotLabelDlpPolicy.ps1"
pytestmark = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")


def run_ps(tmp_path, body):
    h = tmp_path / "h.ps1"
    h.write_text(body, encoding="utf-8")
    return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(h)], capture_output=True, text=True, timeout=120)


def test_snapshot_collects_sections_reads_each_site_by_identity_and_records_errors(tmp_path):
    out = tmp_path / "snap.json"
    # Stand-in cmdlets (TEST ONLY). Get-DlpCompliancePolicy is missing on purpose: the section must land in "errors".
    proc = run_ps(tmp_path, f"""
$script:identityCalls = @()
function Get-AdminAuditLogConfig {{ [pscustomobject]@{{ UnifiedAuditLogIngestionEnabled = $true; Other = 1 }} }}
function Get-Label {{ [pscustomobject]@{{ Name='hc'; DisplayName='Highly Confidential'; Guid='00000000-0000-0000-0000-000000000001'; Disabled=$false; ContentType='File' }} }}
function Get-LabelPolicy {{ [pscustomobject]@{{ Name='p'; Enabled=$true; Labels=@('hc') }} }}
function Get-SPOTenant {{ [pscustomobject]@{{ SharingCapability='Disabled'; ShowEveryoneExceptExternalUsersClaim=$false; AllowEveryoneExceptExternalUsersClaimInPrivateSite=$false; DefaultSharingLinkType='Internal' }} }}
function Get-SPOSite {{
  param($Identity)
  if ($Identity) {{ $script:identityCalls += $Identity
     return [pscustomobject]@{{ Url=$Identity; Title='t'; Template='GROUP#0'; SharingCapability='Disabled'; SensitivityLabel='x'; RestrictContentOrgWideSearch=$false; RestrictedAccessControl=$false }} }}
  # list form without properties (as with -Limit/-Filter on the real cmdlet)
  1..3 | ForEach-Object {{ [pscustomobject]@{{ Url="https://contoso.example/sites/s$_" }} }}
}}
. '{SNAP}'
$s = New-CopilotGovernanceSnapshot -MaxSites 2
if ($script:identityCalls.Count -ne 2) {{ throw "expected 2 by-identity reads, got $($script:identityCalls.Count)" }}
if (-not $s.errors.ContainsKey('dlpPolicies')) {{ throw 'dlpPolicies error not recorded' }}
$s | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '{out}' -Encoding utf8
""")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(out.read_text())
    assert data["auditLog"] == {"UnifiedAuditLogIngestionEnabled": True}
    assert data["dlpPolicies"] is None and "dlpPolicies" in data["errors"]
    assert len(data["sites"]) == 2 and data["sites"][0]["SensitivityLabel"] == "x"
    findings = {f.id: f for f in run_checks(load_snapshot(out))}
    assert findings["G01"].status == "pass" and findings["G03"].status == "unknown"


def test_dlp_script_dry_run_creates_nothing_and_apply_calls_cmdlets_in_simulation(tmp_path):
    proc = run_ps(tmp_path, f"""
$global:created = @()
function Get-Label {{ param() @([pscustomobject]@{{ DisplayName='Highly Confidential'; Name='hc'; Guid='11111111-1111-1111-1111-111111111111' }},
                               [pscustomobject]@{{ DisplayName='General'; Name='gen'; Guid='22222222-2222-2222-2222-222222222222' }}) }}
function New-DlpCompliancePolicy {{ param($Name,$Locations,$EnforcementPlanes,$Mode) $global:created += "policy:$Name|$Mode|$($EnforcementPlanes -join ',')|$Locations" }}
function New-DlpComplianceRule {{ param($Name,$Policy,$AdvancedRule,$RestrictAccess) $global:created += "rule:$Name|$($RestrictAccess[0].setting)=$($RestrictAccess[0].value)|$AdvancedRule" }}
# dry run
& '{DLP}' -LabelName 'Highly Confidential' | Out-Null
if ($global:created.Count -ne 0) {{ throw 'dry run created something' }}
# apply
& '{DLP}' -LabelName 'Highly Confidential' -Apply | Out-Null
if ($global:created.Count -ne 2) {{ throw "expected policy+rule, got $($global:created.Count)" }}
$global:created | ForEach-Object {{ Write-Output $_ }}
# unknown label must fail
try {{ & '{DLP}' -LabelName 'Nope' -Apply; throw 'should have failed' }} catch {{ if ($_.Exception.Message -notlike "*matched 0*") {{ throw }} }}
""")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    out = proc.stdout
    pol = out[out.index("policy:"):out.index("rule:")]
    rule = out[out.index("rule:"):]
    assert pol.startswith("policy:MG Lab - Copilot: block labelled content|TestWithoutNotifications|CopilotExperiences|")
    assert "470f2276-e011-4e9d-a6ec-20768be3a4b0" in pol and '"Tenant"' in pol
    assert "ExcludeContentProcessing=Block" in rule and "11111111-1111-1111-1111-111111111111" in rule
    assert "22222222" not in rule and '"type": "Sensitivity"' in rule


def test_scripts_parse_cleanly():
    for script in (SNAP, DLP):
        cmd = f"$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e);if($e.Count){{$e|Out-String;exit 1}}"
        r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
