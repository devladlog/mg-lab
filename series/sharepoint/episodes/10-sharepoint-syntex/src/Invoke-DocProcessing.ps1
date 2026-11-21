#Requires -Version 7.2
<#
.SYNOPSIS
    Plan, pre-flight and cost of SharePoint document processing (formerly Syntex): lint the plan, estimate the monthly
    cost, check sample files before they reach a library; then, against the lab tenant: upload the sample files and read
    the library back to see what the model did.

.EXAMPLE
    ./Invoke-DocProcessing.ps1 -PlanPath ./bad/bad-docproc.json                                   # lint + cost, no tenant
.EXAMPLE
    ./Invoke-DocProcessing.ps1 -PlanPath ./docproc/contoso-docproc.json -SamplesPath ./sample-files   # + pre-flight of the files
.EXAMPLE
    $t = @{ TenantUrl = 'https://contoso.sharepoint.com'; ClientId = '00000000-0000-0000-0000-000000000000' }
    ./Invoke-DocProcessing.ps1 -PlanPath ./docproc/contoso-docproc.json @t -Upload ./sample-files/inbox -WhatIf
    ./Invoke-DocProcessing.ps1 -PlanPath ./docproc/contoso-docproc.json @t -Upload ./sample-files/inbox
    ./Invoke-DocProcessing.ps1 -PlanPath ./docproc/contoso-docproc.json @t -Report
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PlanPath,
    [string]$SamplesPath,
    [string]$TenantUrl,
    [string]$ClientId,
    [string]$Upload,
    [switch]$Report
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgDocProc.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0,-7} {1}  {2}' -f $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "              $($f.Message)"
    }
}

function Show-Count($Findings) {
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } elseif ($w) { 'Yellow' } else { 'Green' })
}

function Show-Cost($Rows) {
    foreach ($r in $Rows) { Write-Host ('  {0,-22} {1,-26} {2,10:N0} x {3,-6} = {4,9:N2} USD' -f $r.Model, $r.Type, $r.Transactions, $r.Rate, $r.Usd) }
    Write-Host ('  {0,-22} {1,-26} {2,31:N2} USD' -f 'Total per month', '', ($Rows | Measure-Object Usd -Sum).Sum) -ForegroundColor Cyan
}

# 1. Lint and cost: no tenant needed
$plan = Import-MgJson -Path $PlanPath
Write-Host "Document processing plan: $PlanPath" -ForegroundColor Cyan
$all = @(Test-MgDocProcPlan -Plan $plan)
Show-Findings $all
Show-Count $all
$e = Get-MgProp $plan 'expected'
if ($e) {
    Write-Host ("Cost, from the plan ({0} files a month per library, {1} pages each, {2} updates each):" -f $e.docsPerMonth, $e.pagesPerDoc, $e.updatesPerDoc) -ForegroundColor Cyan
    Show-Cost @(Get-MgCostEstimate -Plan $plan)
}

# 2. Pre-flight of real files, per model
if ($SamplesPath) {
    $files = @(Get-ChildItem -LiteralPath $SamplesPath -File -Recurse | Sort-Object FullName)
    foreach ($m in @($plan.models | Where-Object { $_.type -in 'unstructured', 'prebuilt-contract', 'prebuilt-invoice', 'prebuilt-receipt', 'prebuilt-simple', 'prebuilt-sensitive-info' })) {
        Write-Host "Pre-flight for '$($m.name)' ($($m.type)):" -ForegroundColor Cyan
        $found = @()
        foreach ($f in $files) {
            $p = Get-MgBillablePages -Path $f.FullName -ModelType $m.type
            Write-Host ('  {0,-28} {1,4} page(s)  {2}' -f $f.Name, $(if ($null -eq $p.Pages) { '?' } else { $p.Pages }), $p.Note)
            $found += @(Test-MgFile -Path $f.FullName -ModelType $m.type)
        }
        Show-Findings $found
        $rows = @($files | ForEach-Object { Get-MgBillablePages -Path $_.FullName -ModelType $m.type })
        $one = [pscustomobject]@{ models = @($m); expected = $e }
        Write-Host '  one upload of these files:' -ForegroundColor Cyan
        Show-Cost @(Get-MgCostEstimate -Plan $one -Files $rows -UpdatesPerDoc 0)
    }
}
if (-not $TenantUrl) { return }
if (@($all | Where-Object Severity -eq 'Error').Count) { throw 'Fix the errors before touching the tenant.' }

# 3. Tenant: the site of the first library of the plan
if (-not $ClientId) { throw 'Provide -ClientId (your own Entra app for PnP, delegated permissions).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$model = @($plan.models)[0]
$libPath = @($model.appliesTo)[0]
$siteRel = ($libPath -replace '^(/(?:sites|teams)/[^/]+).*', '$1')
$library = ($libPath.TrimEnd('/') -split '/')[-1]
$conn = Connect-PnPOnline -Url ($TenantUrl.TrimEnd('/') + $siteRel) -ClientId $ClientId -DeviceLogin -ReturnConnection

if ($Upload) {
    Write-Host "Upload to $siteRel/$library :" -ForegroundColor Cyan
    Send-MgSampleFiles -Path $Upload -Library $library -Connection $conn -WhatIf:$WhatIfPreference |
        ForEach-Object { Write-Host ('{0,-8} {1,-24} {2}' -f $_.Action, $_.Target, $_.Detail) }
}
if ($Report) {
    Write-Host "Library $library vs model '$($model.name)':" -ForegroundColor Cyan
    $titles = @($model.extractors | ForEach-Object { $_.name })
    $state = Get-MgLibraryState -Library $library -ColumnTitles $titles -Connection $conn
    $ctName = Get-MgProp $model 'contentType' $model.name
    $r = Get-MgExtractionReport -Items $state.Items -ContentType $ctName -Columns @($titles | Where-Object { $_ -notin @($state.MissingColumns) })
    Write-Host ("  files: {0}  classified: {1}  not classified: {2}  of type '{3}': {4}" -f $r.Files, $r.Classified, $r.Unclassified, $ctName, $r.OfContentType)
    foreach ($c in $r.Columns) { Write-Host ('  {0,-18} filled {1}, empty {2}' -f $c.Column, $c.Filled, $c.Empty) }
    $f = @(Test-MgLibraryLive -Model $model -State $state)
    Show-Findings $f; Show-Count $f
}
