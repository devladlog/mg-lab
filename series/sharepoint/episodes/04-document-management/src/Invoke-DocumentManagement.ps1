#Requires -Version 7.2
<#
.SYNOPSIS
    Lint a document management design (and its filing plan), show how a folder of files would be filed, then
    (optionally) provision it with PnP PowerShell, file the documents and audit the library.

.EXAMPLE
    ./Invoke-DocumentManagement.ps1 -DesignPath ./bad/legacy-documents.json                    # lint only
.EXAMPLE
    ./New-SampleDocuments.ps1 -Path ./sample-files
    ./Invoke-DocumentManagement.ps1 -DesignPath ./docmgmt/supplier-documents.json -PlanPath ./docmgmt/filing-plan.json -FilesPath ./sample-files
.EXAMPLE
    ./Invoke-DocumentManagement.ps1 -DesignPath ... -PlanPath ... -FilesPath ./sample-files `
        -SiteUrl https://contoso.sharepoint.com/sites/Purchasing -ClientId 00000000-0000-0000-0000-000000000000 -WhatIf
.EXAMPLE
    ./Invoke-DocumentManagement.ps1 -DesignPath ... -Audit -SiteUrl ... -ClientId ...
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$DesignPath,
    [string]$PlanPath,
    [string]$FilesPath,
    [string]$SiteUrl,
    [string]$ClientId,
    [switch]$IncludeIncomplete,
    [switch]$Audit,
    [switch]$SkipProvisioning,
    [datetime]$Today = (Get-Date).Date
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgDocMgmt.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0,-7} {1}  {2}' -f $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "               $($f.Message)"
    }
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } else { 'Yellow' })
}

function Show-Steps { process { Write-Host ('{0,-17} {1,-45} {2}' -f $_.Action, $_.Target, $_.Detail) } }

# 1. Lint the design and the plan: no tenant needed
$design = Import-MgJson -Path $DesignPath
$plan = if ($PlanPath) { Import-MgJson -Path $PlanPath } else { $null }
$findings = @(Test-MgDocDesign -Design $design -Plan $plan)
if ($plan) { $findings += @(Test-MgFilingPlan -Plan $plan -Design $design) }
Write-Host "Lint: $DesignPath$(if ($PlanPath) { " + $PlanPath" })" -ForegroundColor Cyan
Show-Findings $findings
$hasErrors = @($findings | Where-Object Severity -eq 'Error').Count -gt 0

# 2. Filing plan for a folder of files: no tenant needed
if ($plan -and $FilesPath) {
    Write-Host "Filing plan: $FilesPath" -ForegroundColor Cyan
    foreach ($r in Resolve-MgFilingPlan -Plan $plan -Design $design -FileName (Get-ChildItem -LiteralPath $FilesPath -File | Sort-Object Name).Name) {
        $color = @{ Ready = 'Green'; Incomplete = 'Yellow'; Invalid = 'Red'; Unmatched = 'DarkGray' }[$r.Status]
        $where = if ($r.ContentType) { "$($r.ContentType) -> $($r.Folder)" } else { '' }
        Write-Host ('{0,-11} {1,-54} {2}' -f $r.Status, $r.FileName, $where) -ForegroundColor $color
        if ($r.Problem) { Write-Host "            $($r.Problem)" -ForegroundColor DarkGray }
    }
}
if (-not $SiteUrl) { return }
if ($hasErrors) { throw 'The design or the plan has errors. Fix them before provisioning.' }

# 3. Tenant
if (-not $ClientId) { throw 'Provide -ClientId (your own Entra app for PnP, delegated permissions).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$conn = Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin -ReturnConnection

if (-not $SkipProvisioning -and -not $Audit) {
    Invoke-MgDocMgmtProvisioning -Design $design -Connection $conn | Show-Steps
}
if ($plan -and $FilesPath -and -not $Audit) {
    Invoke-MgFiling -Plan $plan -Design $design -Path $FilesPath -IncludeIncomplete:$IncludeIncomplete -Connection $conn | Show-Steps
}
if (-not $WhatIfPreference) {
    foreach ($lib in @($design.libraries)) {
        Write-Host "Audit (live): $($lib.title)" -ForegroundColor Cyan
        Show-Findings @(Get-MgLibraryAudit -Design $design -Library $lib.title -Today $Today -Connection $conn)
    }
}
