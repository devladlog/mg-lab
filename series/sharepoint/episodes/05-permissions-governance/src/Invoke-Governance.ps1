#Requires -Version 7.2
<#
.SYNOPSIS
    Lint a governance policy, audit a site's permissions and sharing against it, and (optionally) fix what can be
    fixed safely. Works offline on a saved snapshot, or live against a site with PnP PowerShell.

.EXAMPLE
    ./Invoke-Governance.ps1 -PolicyPath ./bad/loose.policy.json                                         # lint only
.EXAMPLE
    ./Invoke-Governance.ps1 -PolicyPath ./governance/purchasing.policy.json -SnapshotPath ./fixtures/drifted.snapshot.json
.EXAMPLE
    ./Invoke-Governance.ps1 -PolicyPath ./governance/purchasing.policy.json -SiteUrl https://contoso.sharepoint.com/sites/Purchasing `
        -ClientId 00000000-0000-0000-0000-000000000000 -SensitivityLabelId 00000000-0000-0000-0000-000000000000 -ExportSnapshot ./snapshots/before.json
.EXAMPLE
    ./Invoke-Governance.ps1 -PolicyPath ... -SiteUrl ... -ClientId ... -SensitivityLabelId ... -Fix -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PolicyPath,
    [string]$SnapshotPath,
    [string]$SiteUrl,
    [string]$ClientId,
    [string]$SensitivityLabelId,
    [string]$ExportSnapshot,
    [switch]$Fix
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgGovernance.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0,-7} {1}  {2}' -f $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "               $($f.Message)"
    }
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    $n = @($Findings | Where-Object Fix).Count
    Write-Host "$e error(s), $w warning(s); $n can be fixed automatically" -ForegroundColor $(if ($e) { 'Red' } else { 'Yellow' })
}

function Show-Summary($Snapshot) {
    $s = Get-MgScopeSummary -Snapshot $Snapshot
    Write-Host ("Site {0}: sharing '{1}', default link {2}, label {3}" -f $s.Site, $s.Sharing, $s.DefaultLink, $s.Label) -ForegroundColor Cyan
    Write-Host ("     {0} groups, {1} lists and {2} items with unique permissions, {3} sharing links" -f $s.Groups, $s.UniqueLists, $s.UniqueItems, $s.SharingLinks) -ForegroundColor Cyan
}

# 1. Lint the policy: no tenant needed
$policy = Import-MgJson -Path $PolicyPath
if ($SensitivityLabelId -and $policy.PSObject.Properties['sensitivityLabel']) { $policy.sensitivityLabel | Add-Member -NotePropertyName id -NotePropertyValue $SensitivityLabelId -Force }
Write-Host "Policy: $PolicyPath" -ForegroundColor Cyan
$lint = @(Test-MgGovernancePolicy -Policy $policy)
Show-Findings $lint
if (-not $SnapshotPath -and -not $SiteUrl) { return }
if (@($lint | Where-Object Severity -eq 'Error').Count) { throw 'The policy has errors. Fix them before auditing a site.' }

# 2. Snapshot: from a file, or read live
$conn = $null
if ($SiteUrl) {
    if (-not $ClientId) { throw 'Provide -ClientId (your own Entra app for PnP, delegated permissions).' }
    Import-Module PnP.PowerShell -ErrorAction Stop
    $conn = Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin -ReturnConnection
    $snapshot = Get-MgPermissionSnapshot -SiteUrl $SiteUrl -Connection $conn
    if ($ExportSnapshot) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ExportSnapshot) | Out-Null
        $snapshot | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ExportSnapshot -Encoding utf8
        Write-Host "Snapshot saved: $ExportSnapshot" -ForegroundColor DarkGray
    }
}
else {
    $snapshot = Import-MgJson -Path $SnapshotPath
}

# 3. Audit + remediation plan
Show-Summary $snapshot
$findings = @(Test-MgPermissionSnapshot -Snapshot $snapshot -Policy $policy)
Show-Findings $findings
$plan = @(Get-MgRemediationPlan -Findings $findings)
if ($plan.Count) {
    Write-Host 'Remediation plan:' -ForegroundColor Cyan
    foreach ($p in $plan) {
        $detail = ($p.Fix.PSObject.Properties | Where-Object Name -ne 'Action' | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ' '
        Write-Host ('  {0,-21} {1,-6} {2}' -f $p.Fix.Action, $p.Rule, $detail)
    }
}
if (-not $Fix) { return }
if (-not $SiteUrl) { throw '-Fix needs -SiteUrl: a snapshot file can only be audited.' }

# 4. Fix, then audit again
Invoke-MgRemediation -SiteUrl $SiteUrl -Plan $plan -Connection $conn -WhatIf:$WhatIfPreference |
    ForEach-Object { Write-Host ('{0,-21} {1,-6} {2} {3}' -f $_.Action, $_.Rule, $(if ($_.Done) { 'done   ' } else { 'what-if' }), $_.Detail) }
if ($WhatIfPreference) { return }
Write-Host 'Audit after remediation:' -ForegroundColor Cyan
$after = Get-MgPermissionSnapshot -SiteUrl $SiteUrl -Connection $conn
Show-Summary $after
Show-Findings @(Test-MgPermissionSnapshot -Snapshot $after -Policy $policy)
