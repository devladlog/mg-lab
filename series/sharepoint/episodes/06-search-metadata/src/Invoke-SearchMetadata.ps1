#Requires -Version 7.2
<#
.SYNOPSIS
    Lint the term set, the search plan and every test query; then, against the lab site: provision the term set and
    the Category column and tag the files, check the search schema mappings, request a re-index and run the search
    tests.

.EXAMPLE
    ./Invoke-SearchMetadata.ps1 -PlanPath ./bad/bad-search-plan.json                                   # lint only
.EXAMPLE
    ./Invoke-SearchMetadata.ps1 -PlanPath ./search/search-plan.json -TermSetPath ./search/purchasing-categories.termset.json `
        -TestsPath ./search/search-tests.json
.EXAMPLE
    ./Invoke-SearchMetadata.ps1 -PlanPath ... -TermSetPath ... -SiteUrl https://contoso.sharepoint.com/sites/Purchasing `
        -ClientId 00000000-0000-0000-0000-000000000000 -Provision -WhatIf
.EXAMPLE
    ./Invoke-SearchMetadata.ps1 -PlanPath ... -TermSetPath ... -TestsPath ... -SiteUrl ... -ClientId ... -CheckMapping -Reindex
    ./Invoke-SearchMetadata.ps1 -PlanPath ... -TermSetPath ... -TestsPath ... -SiteUrl ... -ClientId ... -RunTests
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PlanPath,
    [string]$TermSetPath,
    [string]$TestsPath,
    [string]$SiteUrl,
    [string]$ClientId,
    [switch]$Provision,
    [switch]$CheckMapping,
    [switch]$Reindex,
    [switch]$RunTests,
    [datetime]$Today = (Get-Date).Date
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgSearchMeta.psm1') -Force

function Show-Findings($Findings, [string]$Indent = '') {
    if (-not $Findings) { Write-Host "${Indent}No findings." -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0}{1,-7} {2}  {3}' -f $Indent, $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "$Indent               $($f.Message)"
    }
}

function Show-Count($Findings) {
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } elseif ($w) { 'Yellow' } else { 'Green' })
}

function Show-Steps { process { Write-Host ('{0,-13} {1,-50} {2}' -f $_.Action, $_.Target, $_.Detail) } }

# 1. Lint: no tenant needed
$plan = Import-MgJson -Path $PlanPath
$termSet = if ($TermSetPath) { Import-MgJson -Path $TermSetPath } else { $null }
$tests = if ($TestsPath) { Import-MgJson -Path $TestsPath } else { $null }
$all = @()
if ($termSet) {
    Write-Host "Term set: $TermSetPath" -ForegroundColor Cyan
    $f = @(Test-MgTermSet -TermSet $termSet); Show-Findings $f; $all += $f
}
Write-Host "Search plan: $PlanPath" -ForegroundColor Cyan
$f = @(Test-MgSearchPlan -Plan $plan -TermSet $termSet); Show-Findings $f; $all += $f
if ($tests) {
    Write-Host "Queries: $TestsPath" -ForegroundColor Cyan
    $site = if ($SiteUrl) { $SiteUrl } else { 'https://contoso.sharepoint.com/sites/Purchasing' }
    foreach ($t in $tests.tests) {
        $kql = ConvertTo-MgKql -Template $t.query -Plan $plan -TermSet $termSet -SiteUrl $site -Today $Today
        $f = @(Test-MgKql -Query $kql -Plan $plan -Target $t.name)
        $mark = if (@($f | Where-Object Severity -eq 'Error').Count) { 'x' } elseif ($f.Count) { '!' } else { 'ok' }
        Write-Host ('{0,-3}{1}' -f $mark, $t.name) -ForegroundColor $(@{ x = 'Red'; '!' = 'Yellow'; ok = 'Green' }[$mark])
        Write-Host "   $kql" -ForegroundColor DarkGray
        Show-Findings $f '   '
        if (-not ($t.PSObject.Properties['lintOnly'] -and $t.lintOnly)) { $all += $f }
    }
}
Show-Count $all
if (-not $SiteUrl) { return }
if (@($all | Where-Object Severity -eq 'Error').Count) { throw 'Fix the errors before touching the site (lint-only queries are allowed to fail).' }

# 2. Tenant
if (-not $ClientId) { throw 'Provide -ClientId (your own Entra app for PnP, delegated permissions).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$conn = Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin -ReturnConnection

if ($Provision) {
    if (-not $termSet) { throw '-Provision needs -TermSetPath.' }
    Write-Host 'Provisioning:' -ForegroundColor Cyan
    Invoke-MgTaxonomyProvisioning -TermSet $termSet -Connection $conn -WhatIf:$WhatIfPreference | Show-Steps
    Invoke-MgCategoryColumn -Plan $plan -Connection $conn -WhatIf:$WhatIfPreference | Show-Steps
    Invoke-MgCategoryTagging -Plan $plan -TermSet $termSet -Connection $conn -WhatIf:$WhatIfPreference | Show-Steps
}
if ($CheckMapping) {
    Write-Host 'Search schema (site collection):' -ForegroundColor Cyan
    $live = @(Get-MgSiteSearchMapping -Connection $conn)
    foreach ($m in $live) { Write-Host ('  {0,-20} alias {1,-18} <- {2}' -f $m.Name, (@($m.Aliases) -join ','), (@($m.Mappings) -join ', ')) }
    $f = @(Test-MgSearchMapping -Plan $plan -Mappings $live); Show-Findings $f; Show-Count $f
}
if ($Reindex -and $PSCmdlet.ShouldProcess($plan.library, 'Request re-index')) {
    Request-PnPReindexList -Identity $plan.library -Connection $conn
    Write-Host "Re-index requested for '$($plan.library)': it happens at the next crawl." -ForegroundColor Cyan
}
if ($RunTests) {
    if (-not $tests) { throw '-RunTests needs -TestsPath.' }
    Write-Host 'Search tests:' -ForegroundColor Cyan
    $results = @(Invoke-MgSearchTest -Tests $tests -Plan $plan -TermSet $termSet -SiteUrl $SiteUrl -Today $Today -Connection $conn)
    foreach ($r in $results) {
        Write-Host ('{0,-5} {1,-45} {2} result(s)' -f $(if ($r.Passed) { 'PASS' } else { 'FAIL' }), $r.Name, $r.Count) -ForegroundColor $(if ($r.Passed) { 'Green' } else { 'Red' })
        foreach ($p in $r.Problems) { Write-Host "      $p" -ForegroundColor DarkGray }
    }
    Write-Host ('{0} passed, {1} failed' -f @($results | Where-Object Passed).Count, @($results | Where-Object { -not $_.Passed }).Count)
}
