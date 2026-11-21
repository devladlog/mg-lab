#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #9 (Licensing Optimization). The audit is read-only; -Reclaim and -Restore are the only writes.
.EXAMPLE
    # offline: analyse a saved snapshot (the fictional fixture)
    ./Invoke-LicensingOptimization.ps1 -Snapshot ../tests/fixtures/snapshot.json -ConfigFile ../tests/fixtures/licensing.test.json -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/licensing-audit.md
.EXAMPLE
    # needs tenant: audit, and save the snapshot (tenant data: never commit it)
    ./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -SaveSnapshot ./snapshot.lab.json -OutFile ./audit.lab.md
.EXAMPLE
    # needs tenant: preview, then really remove the licences the plan allows (writes a rollback file first)
    ./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -Reclaim -RollbackFile ./rollback.lab.json -WhatIf
    ./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -Reclaim -RollbackFile ./rollback.lab.json
    ./Invoke-LicensingOptimization.ps1 -Restore ./rollback.lab.json
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'licensing.json'),
    [string]$Snapshot,
    [string]$SaveSnapshot,
    [string]$OutFile,
    [datetimeoffset]$AsOf = [datetimeoffset]::UtcNow,
    [switch]$Reclaim,
    [string]$RollbackFile,
    [string]$Restore
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'LicensingOptimization/LicensingOptimization.psd1') -Force

function Show-Table($Data, [object[]]$Property) {
    # Out-String -Width: without a console (CI, redirected output) the default width is 0 and Format-Table prints nothing.
    $w = try { [Math]::Max(140, $Host.UI.RawUI.WindowSize.Width) } catch { 180 }
    $a = @{ AutoSize = $true; Wrap = $true }; if ($Property) { $a.Property = $Property }
    ($Data | Format-Table @a | Out-String -Width $w).TrimEnd() | Write-Output
}
function Connect-LOGraph([string[]]$Scopes) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' }
    $ctx = Get-MgContext
    if (-not $ctx -or ($Scopes | Where-Object { $_ -notin $ctx.Scopes })) { Connect-MgGraph -Scopes $Scopes -NoWelcome | Out-Null }
}

if ($Restore) {
    Connect-LOGraph @('LicenseAssignment.ReadWrite.All', 'LicenseAssignment.Read.All')
    Show-Table @(Restore-LOReclaim -RollbackFile $Restore -WhatIf:$WhatIfPreference)
    return
}

$config = Get-LOConfig -Path $ConfigFile
if ($Snapshot) {
    if ($Reclaim) { throw '-Reclaim needs live data: run it without -Snapshot.' }
    $s = Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json
    $skus = @($s.skus); $users = @($s.users); $protected = @($s.protectedUserIds)
    Write-Output "Snapshot collected $(([datetimeoffset]$s.collectedAt).ToString('yyyy-MM-dd HH:mm')) UTC ($($s.note))"
}
else {
    $scopes = @('LicenseAssignment.Read.All', 'User.Read.All', 'AuditLog.Read.All', 'RoleManagement.Read.Directory')
    if ($Reclaim) { $scopes += 'LicenseAssignment.ReadWrite.All' }
    Connect-LOGraph $scopes
    $skus = @(Get-LOSku); $users = @(Get-LOUser)
    $protected = if ($config.protectAdminRoleMembers) { @(Get-LOProtectedUserId) } else { @() }
    if ($SaveSnapshot) { [pscustomobject]@{ collectedAt = [datetimeoffset]::UtcNow.ToString('o'); note = 'live'; skus = $skus; users = $users; protectedUserIds = $protected } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $SaveSnapshot }
}

$findings = @(Get-LOLicenceFinding -Skus $skus -Users $users -ProtectedUserId $protected -Config $config -Now $AsOf)
$seats = @(Get-LOSeatSummary -Skus $skus -Config $config)
$savings = Get-LOSavingSummary -Findings $findings -Config $config
$plan = @(Get-LOReclaimPlan -Findings $findings -Config $config)

Show-Table $findings @('Severity', 'Rule', 'User', 'Sku', 'Source', 'Reclaimable', 'MonthlySaving')
Write-Output ("{0} user(s), {1} finding(s); reclaimable seats {2}{3}" -f $users.Count, $findings.Count, $savings.Seats,
    $(if ($savings.PricedSeats -gt 0) { ", potential $($savings.MonthlyTotal) $($savings.Currency) per month" } else { ' (no prices configured)' }))
if ($seats.Count) { Write-Output 'Seats paid for but not assigned:'; Show-Table $seats }
$notAllowed = @($findings | Where-Object { $_.Reclaimable -and $_.Rule -in $config.reclaim.rules } | Where-Object { $_.Sku -notin @($config.reclaim.allowedSkuPartNumbers) } | Select-Object -ExpandProperty Sku -Unique)
Write-Output ("Reclaim plan: {0} removal(s) allowed by reclaim.allowedSkuPartNumbers{1}" -f $plan.Count, $(if ($notAllowed.Count) { "; reclaimable but not allowed: $($notAllowed -join ', ')" } else { '' }))
if ($plan.Count) { Show-Table $plan @('UserPrincipalName', 'SkuPartNumber', 'Rules') }
if ($OutFile) { ConvertTo-LOMarkdown -Findings $findings -Seats $seats -Savings $savings -Plan $plan -UsersScanned $users.Count -GeneratedOn $AsOf.ToString('yyyy-MM-dd') -Currency $config.prices.currency | Set-Content -LiteralPath $OutFile -Encoding utf8; Write-Output "Report written to $OutFile" }

if ($Reclaim) {
    if (-not $RollbackFile) { throw '-Reclaim needs -RollbackFile (a new file name).' }
    Show-Table @(Invoke-LOReclaim -Plan $plan -RollbackFile $RollbackFile -WhatIf:$WhatIfPreference)
}
