#Requires -Version 7.2
<#
.SYNOPSIS
    The Monday governance check for a Power BI / Fabric tenant: tenant settings drift, orphaned workspaces, metadata scan + rules, yesterday's activity.

.DESCRIPTION
    Read only. Nothing in the tenant is changed. Writes out/governance-<date>.md, findings-<date>.json and scan-<date>.json.
    Run Connect-PowerBIServiceAccount first, as a Fabric administrator (or use a service principal that is allowed to call the read-only admin APIs).
    The tenant settings step also needs -FabricToken (api.fabric.microsoft.com audience) and a baseline file.

.PARAMETER ScanResultPath  Apply the rules to a saved scan result and do not call the scanner (also useful to re-run the rules on yesterday's file).
.PARAMETER FailOn          Exit code 1 when a finding of this severity (or worse) exists: error (default), warning, or none.

.EXAMPLE
    ./Invoke-GovernanceAudit.ps1 -Date (Get-Date).AddDays(-1) -BaselinePath ./policy/tenant-baseline.json -FabricToken $fabric
#>
[CmdletBinding()]
param(
    [datetime] $Date = [datetime]::UtcNow.Date.AddDays(-1),
    [string] $BaselinePath,
    [securestring] $FabricToken,
    [string] $OutDir = (Join-Path (Get-Location) 'out'),
    [string] $ScanResultPath,
    [switch] $ExcludePersonal,
    [switch] $SkipActivity,
    [ValidateRange(0, 600)][int] $PollSeconds = 30,
    [ValidateSet('error', 'warning', 'none')][string] $FailOn = 'error'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PbiGovernance' 'PbiGovernance.psd1') -Force
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$stamp = $Date.ToString('yyyy-MM-dd')

# 1. tenant settings drift
$drift = $null
if ($BaselinePath) {
    Write-Host 'Tenant settings: reading and comparing with the baseline'
    $drift = @(Compare-PbiTenantSetting -Current @(Get-PbiTenantSetting -FabricToken $FabricToken) -BaselinePath $BaselinePath -IgnoreNew)
}

# 2. workspaces without an admin
$orphans = $null
if (-not $ScanResultPath) {
    Write-Host 'Workspaces: looking for workspaces without an Admin'
    $orphans = @(Get-PbiOrphanedWorkspace)
}

# 3. scan and rules
if ($ScanResultPath) {
    $scan = Get-Content -Raw -Path $ScanResultPath | ConvertFrom-Json -Depth 32
}
else {
    $ids = @(Get-PbiModifiedWorkspace -ExcludePersonal:$ExcludePersonal)
    Write-Host "Scanner: $($ids.Count) workspace(s)"
    $scan = Invoke-PbiWorkspaceScan -WorkspaceId $ids -DatasourceDetails -DatasetSchema -GetArtifactUsers -PollSeconds $PollSeconds
    $scan | ConvertTo-Json -Depth 32 | Set-Content -Path (Join-Path $OutDir "scan-$stamp.json") -Encoding utf8
}
$findings = @(Test-PbiGovernance -ScanResult $scan)
$findings | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutDir "findings-$stamp.json") -Encoding utf8

# 4. activity of the day
$summary = $null
if (-not $SkipActivity) {
    Write-Host "Activity: $stamp (UTC)"
    $summary = Get-PbiActivitySummary -Event @(Get-PbiActivityEvent -Date $Date)
}

$md = New-PbiGovernanceReport -Date $Date -Findings $findings -Drift $drift -ActivitySummary $summary -Orphans $orphans -WorkspacesScanned @($scan.workspaces).Count
$mdPath = Join-Path $OutDir "governance-$stamp.md"
$md | Set-Content -Path $mdPath -Encoding utf8
Write-Host "Report: $mdPath"

$rank = @{ error = 2; warning = 1; info = 0 }
if ($FailOn -ne 'none' -and @($findings | Where-Object { $rank[$_.Severity] -ge $rank[$FailOn] }).Count -gt 0) {
    Write-Host "Findings at '$FailOn' or worse: exit 1"
    exit 1
}
