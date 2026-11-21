#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #11 (SharePoint Online administration). The audit is read-only; -Remediate and -Restore are the only writes.
.EXAMPLE
    # offline: analyse saved data (the fictional fixtures)
    ./Invoke-SharePointAdmin.ps1 -BaselineFile ../tests/fixtures/baseline.test.json -SettingsFile ../tests/fixtures/settings.json -UsageFile ../tests/fixtures/siteusage.csv -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/sharepoint-report.md
.EXAMPLE
    # needs tenant: audit, then preview and apply the remediation, then put it back
    ./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -OutFile ./report.lab.md
    ./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -Remediate -RollbackFile ./rollback.lab.json -WhatIf
    ./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -Remediate -RollbackFile ./rollback.lab.json
    ./Invoke-SharePointAdmin.ps1 -Restore ./rollback.lab.json
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string]$BaselineFile = (Join-Path $PSScriptRoot 'sharepoint-baseline.json'),
    [string]$SettingsFile,
    [string]$UsageFile,
    [ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180',
    [string]$OutFile,
    [datetimeoffset]$AsOf = [datetimeoffset]::UtcNow,
    [switch]$Remediate,
    [string]$RollbackFile,
    [string]$Restore
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'SharePointAdmin/SharePointAdmin.psd1') -Force

function Show-Table($Data, [object[]]$Property) {
    # Out-String -Width: without a console (CI, redirected output) the default width is 0 and Format-Table prints nothing.
    $w = try { [Math]::Max(140, $Host.UI.RawUI.WindowSize.Width) } catch { 180 }
    $a = @{ AutoSize = $true; Wrap = $true }; if ($Property) { $a.Property = $Property }
    ($Data | Format-Table @a | Out-String -Width $w).TrimEnd() | Write-Output
}
function Connect-SPAGraph([string[]]$Scopes) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' }
    $ctx = Get-MgContext
    if (-not $ctx -or ($Scopes | Where-Object { $_ -notin $ctx.Scopes })) { Connect-MgGraph -Scopes $Scopes -NoWelcome | Out-Null }
}

if ($Restore) {
    Connect-SPAGraph @('SharePointTenantSettings.ReadWrite.All')
    Show-Table @(Restore-SPARemediation -RollbackFile $Restore -WhatIf:$WhatIfPreference)
    return
}

$baseline = Get-SPABaseline -Path $BaselineFile
$offline = [bool]($SettingsFile -or $UsageFile)
if ($offline -and $Remediate) { throw '-Remediate needs the live tenant: run it without -SettingsFile / -UsageFile.' }
if (-not $offline) {
    $scopes = @('SharePointTenantSettings.Read.All', 'Reports.Read.All', 'ReportSettings.Read.All')
    if ($Remediate) { $scopes += 'SharePointTenantSettings.ReadWrite.All' }
    Connect-SPAGraph $scopes
}

$settings = if ($SettingsFile) { Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json } else { Get-SPATenantSetting }
$rows = if ($UsageFile) { @(Import-Csv -LiteralPath $UsageFile) } else { @(Get-SPASiteUsageReport -Period $Period) }
$findings = [System.Collections.Generic.List[object]]::new()
foreach ($f in @(Get-SPASettingFinding -Settings $settings -Baseline $baseline)) { $findings.Add($f) }
$storage = $null
try {
    foreach ($f in @(Get-SPASiteFinding -Rows $rows -Baseline $baseline -Now $AsOf)) { $findings.Add($f) }
    $storage = Get-SPAStorageSummary -Rows $rows -Baseline $baseline
}
catch [System.InvalidOperationException] {
    $priv = if ($offline) { $null } else { Get-SPAReportPrivacy }
    Write-Warning ($_.Exception.Message + $(if ($null -ne $priv) { " (adminReportSettings.displayConcealedNames = $priv)" } else { '' }))
}
$plan = @(Get-SPARemediationPlan -Findings $findings -Baseline $baseline)

Show-Table @($findings | Sort-Object { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] }, Rule) @('Severity', 'Rule', 'Target', 'Detail')
Write-Output ("{0} finding(s); remediation plan {1} change(s) allowed by remediate.allowedSettings" -f $findings.Count, $plan.Count)
if ($storage) { Write-Output ("{0} site(s) in the report, {1} GB used" -f $storage.Sites, $storage.UsedGB) }
if ($plan.Count) { Show-Table $plan @('Setting', 'Current', 'Expected') }
if ($OutFile) { ConvertTo-SPAMarkdown -Findings $findings -Storage $storage -Plan $plan -GeneratedOn $AsOf.ToString('yyyy-MM-dd') -Period $Period | Set-Content -LiteralPath $OutFile -Encoding utf8; Write-Output "Report written to $OutFile" }

if ($Remediate) {
    if (-not $RollbackFile) { throw '-Remediate needs -RollbackFile (a new file name).' }
    Show-Table @(Invoke-SPARemediation -Plan $plan -RollbackFile $RollbackFile -WhatIf:$WhatIfPreference)
}
