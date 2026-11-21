#Requires -Version 7.2
<#
.SYNOPSIS
    Tenant side of DEVLADLOG Microsoft 365 #12 (OneDrive for Business). Read-only: tenant OneDrive settings against a baseline, and the
    OneDrive accounts from the usage report. The PC side is Set-OneDriveSyncPolicy.ps1.
.EXAMPLE
    # offline: analyse saved data (the fictional fixtures)
    ./Invoke-OneDriveAudit.ps1 -BaselineFile ../tests/fixtures/baseline.test.json -SettingsFile ../tests/fixtures/settings.json -UsageFile ../tests/fixtures/onedriveusage.csv -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/onedrive-report.md
.EXAMPLE
    # needs tenant (SharePointTenantSettings.Read.All, Reports.Read.All, ReportSettings.Read.All)
    ./Invoke-OneDriveAudit.ps1 -BaselineFile ./onedrive-baseline.lab.json -OutFile ./report.lab.md
#>
[CmdletBinding()]
param(
    [string]$BaselineFile = (Join-Path $PSScriptRoot 'onedrive-baseline.json'),
    [string]$SettingsFile,
    [string]$UsageFile,
    [ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180',
    [string]$OutFile,
    [datetimeoffset]$AsOf = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OneDriveAdmin/OneDriveAdmin.psd1') -Force

function Show-Table($Data, [object[]]$Property) {
    # Out-String -Width: without a console (CI, redirected output) the default width is 0 and Format-Table prints nothing.
    $w = try { [Math]::Max(140, $Host.UI.RawUI.WindowSize.Width) } catch { 180 }
    $a = @{ AutoSize = $true; Wrap = $true }; if ($Property) { $a.Property = $Property }
    ($Data | Format-Table @a | Out-String -Width $w).TrimEnd() | Write-Output
}

$baseline = Get-ODABaseline -Path $BaselineFile
$offline = [bool]($SettingsFile -or $UsageFile)
if (-not $offline) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' }
    $scopes = @('SharePointTenantSettings.Read.All', 'Reports.Read.All', 'ReportSettings.Read.All')
    $ctx = Get-MgContext
    if (-not $ctx -or ($scopes | Where-Object { $_ -notin $ctx.Scopes })) { Connect-MgGraph -Scopes $scopes -NoWelcome | Out-Null }
}
$settings = if ($SettingsFile) { Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json } else { Get-ODATenantSetting }
$rows = if ($UsageFile) { @(Import-Csv -LiteralPath $UsageFile) } else { @(Get-ODAUsageReport -Period $Period) }

$findings = [System.Collections.Generic.List[object]]::new()
foreach ($f in @(Get-ODASettingFinding -Settings $settings -Baseline $baseline)) { $findings.Add($f) }
$storage = $null
try {
    $default = if ($settings.PSObject.Properties['personalSiteDefaultStorageLimitInMB']) { [long]$settings.personalSiteDefaultStorageLimitInMB } else { 0 }
    foreach ($f in @(Get-ODAAccountFinding -Rows $rows -Baseline $baseline -Now $AsOf -DefaultQuotaMB $default)) { $findings.Add($f) }
    $storage = Get-ODAStorageSummary -Rows $rows -Baseline $baseline
}
catch [System.InvalidOperationException] {
    $priv = if ($offline) { $null } else { Get-ODAReportPrivacy }
    Write-Warning ($_.Exception.Message + $(if ($null -ne $priv) { " (adminReportSettings.displayConcealedNames = $priv)" } else { '' }))
}
Show-Table @($findings | Sort-Object { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] }, Rule) @('Severity', 'Rule', 'Target', 'Detail')
Write-Output ("{0} finding(s)" -f $findings.Count)
if ($storage) { Write-Output ("{0} account(s) in the report, {1} GB used, {2} deleted" -f $storage.Accounts, $storage.UsedGB, $storage.DeletedAccounts) }
if ($OutFile) { ConvertTo-ODAMarkdown -Findings $findings -Storage $storage -GeneratedOn $AsOf.ToString('yyyy-MM-dd') -Period $Period | Set-Content -LiteralPath $OutFile -Encoding utf8; Write-Output "Report written to $OutFile" }
