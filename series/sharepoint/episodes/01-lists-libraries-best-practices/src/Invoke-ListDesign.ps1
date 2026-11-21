#Requires -Version 7.2
<#
.SYNOPSIS
    Lint a list design, then (optionally) provision it, seed fictional items and audit the live result.

.EXAMPLE
    ./Invoke-ListDesign.ps1 -DesignPath ./designs/bad-design.json              # lint only, no tenant
.EXAMPLE
    ./Invoke-ListDesign.ps1 -DesignPath ./designs/purchase-requests.json `
        -SiteUrl https://contoso.sharepoint.com/sites/ListsDemo -ClientId 00000000-0000-0000-0000-000000000000 -WhatIf
.EXAMPLE
    ./Invoke-ListDesign.ps1 -DesignPath ./designs/purchase-requests.json -SiteUrl ... -ClientId ... `
        -SeedItems 40 -RequesterEmail alex.demo@contoso.com
.EXAMPLE
    ./Invoke-ListDesign.ps1 -AuditList "Legacy Requests" -ExpectedItems 60000 -SiteUrl ... -ClientId ...
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Design')]
param(
    [Parameter(ParameterSetName = 'Design', Mandatory)][string]$DesignPath,
    [Parameter(ParameterSetName = 'Audit', Mandatory)][string]$AuditList,
    [Parameter(ParameterSetName = 'Audit')][long]$ExpectedItems = 0,
    [string]$SiteUrl,
    [string]$ClientId,
    [Parameter(ParameterSetName = 'Design')][int]$SeedItems = 0,
    [Parameter(ParameterSetName = 'Design')][string]$RequesterEmail,
    [Parameter(ParameterSetName = 'Design')][switch]$Force
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgListDesign.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0,-7} {1}  {2}' -f $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "               $($f.Message)"
    }
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } elseif ($w) { 'Yellow' } else { 'Green' })
}

function Connect-Lab {
    if (-not $SiteUrl -or -not $ClientId) { throw 'Provide -SiteUrl and -ClientId (your own Entra app for PnP).' }
    Import-Module PnP.PowerShell -ErrorAction Stop
    Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin
}

if ($PSCmdlet.ParameterSetName -eq 'Audit') {
    Connect-Lab
    $audit = Get-MgListAudit -ListTitle $AuditList -ExpectedItems $ExpectedItems
    Write-Host "Audit of '$AuditList' (linted as $($audit.Design.lists[0].expectedItems) items)" -ForegroundColor Cyan
    Show-Findings $audit.Findings
    return
}

# 1. Lint: no tenant needed
$design = Import-MgListDesign -Path $DesignPath
$findings = @(Test-MgListDesign -Design $design)
Write-Host "Lint: $DesignPath" -ForegroundColor Cyan
Show-Findings $findings
if (-not $SiteUrl) { return }
if (@($findings | Where-Object Severity -eq 'Error').Count -and -not $Force) {
    throw 'The design has errors. Fix them (or use -Force for a demo) before provisioning.'
}

# 2. Provision (idempotent, honours -WhatIf)
Connect-Lab
Invoke-MgListProvisioning -Design $design | ForEach-Object { Write-Host ('{0,-12} {1,-45} {2}' -f $_.Action, $_.Target, $_.Detail) }

# 3. Seed fictional items into the first list
if ($SeedItems -gt 0 -and -not $WhatIfPreference) {
    if (-not $RequesterEmail) { throw 'Seeding needs -RequesterEmail (a user in the lab tenant).' }
    $target = $design.lists[0].title
    $batch = New-PnPBatch
    New-MgSampleRequest -Count $SeedItems -RequesterEmail $RequesterEmail | ForEach-Object {
        Add-PnPListItem -List $target -Values $_ -Batch $batch | Out-Null
    }
    Invoke-PnPBatch -Batch $batch
    Write-Host "Seeded $SeedItems items into '$target'." -ForegroundColor Green
}

# 4. Audit what is really in the tenant, linted for the size each list is designed for
if (-not $WhatIfPreference) {
    foreach ($l in $design.lists) {
        $audit = Get-MgListAudit -ListTitle $l.title -ExpectedItems $l.expectedItems
        Write-Host "Audit (live): $($l.title)" -ForegroundColor Cyan
        Show-Findings $audit.Findings
    }
}
