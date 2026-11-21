#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #7 (Intune & Device Management).
.EXAMPLE
    # offline: audit a saved device list (the fictional fixture)
    ./Invoke-IntuneDevices.ps1 -Audit -DevicesFile ../tests/fixtures/devices.json -Now 2026-11-21T12:00:00Z
.EXAMPLE
    # needs tenant: preview, then apply the compliance policy, audit live, sync one device
    ./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy -WhatIf
    ./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy
    ./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -Audit
    ./Invoke-IntuneDevices.ps1 -SyncDeviceName CON-W11-01
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [string]$PolicyFile = (Join-Path $PSScriptRoot 'intune.json'),
    [switch]$ApplyPolicy,
    [switch]$Audit,
    [string]$DevicesFile,
    [string]$SaveDevices,
    [string]$SyncDeviceName,
    [string]$OutFile,
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'IntuneDevices/IntuneDevices.psd1') -Force
$config = Get-IntuneConfig -Path $PolicyFile

function Show-Table($Data, [object[]]$Property) {
    # Out-String -Width: without a console (CI, redirected output) the default width is 0 and Format-Table prints nothing.
    $w = try { [Math]::Max(120, $Host.UI.RawUI.WindowSize.Width) } catch { 160 }
    $args2 = @{ AutoSize = $true; Wrap = $true }; if ($Property) { $args2.Property = $Property }
    ($Data | Format-Table @args2 | Out-String -Width $w).TrimEnd() | Write-Output
}

function Connect-Graph([string[]]$Scopes) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' }
    $ctx = Get-MgContext
    if (-not $ctx -or ($Scopes | Where-Object { $_ -notin $ctx.Scopes })) { Connect-MgGraph -Scopes $Scopes -NoWelcome | Out-Null }
}

if ($ApplyPolicy) {
    Connect-Graph 'DeviceManagementConfiguration.ReadWrite.All'
    Show-Table (Set-IntuneCompliancePolicy -Config $config -WhatIf:$WhatIfPreference) @('Policy', 'Action', @{ n = 'Changes'; e = { @($_.Changes).Name -join ', ' } })
}

if ($Audit -or $SyncDeviceName) {
    if ($DevicesFile) { $devices = @((Get-Content -LiteralPath $DevicesFile -Raw | ConvertFrom-Json).value | Where-Object operatingSystem -eq 'Windows') }
    else {
        Connect-Graph 'DeviceManagementManagedDevices.Read.All'
        $devices = @(Get-IntuneManagedDevice -OperatingSystem Windows)
        if ($SaveDevices) { @{ value = $devices } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveDevices }
    }
}

if ($Audit) {
    $summary = @(Get-IntuneComplianceSummary -Devices $devices)
    $findings = @(Get-IntuneDeviceFinding -Devices $devices -Config $config -Now $Now)
    Show-Table $summary
    Show-Table $findings @('Severity', 'Rule', 'Device', 'Message')
    $by = $findings | Group-Object Severity | ForEach-Object { "$($_.Count) $($_.Name)" }
    Write-Output ("{0} device(s), {1} finding(s): {2}" -f $devices.Count, $findings.Count, ($by -join ' / '))
    if ($OutFile) { ConvertTo-IntuneMarkdown -Summary $summary -Findings $findings -DeviceCount $devices.Count | Set-Content -LiteralPath $OutFile }
}

if ($SyncDeviceName) {
    if ($DevicesFile) { throw '-SyncDeviceName needs the live tenant (it calls Graph).' }
    Connect-Graph 'DeviceManagementManagedDevices.PrivilegedOperations.All'
    $target = @($devices | Where-Object deviceName -eq $SyncDeviceName)
    if ($target.Count -ne 1) { throw "Expected exactly one managed device named '$SyncDeviceName', found $($target.Count)." }
    Show-Table ($target | Invoke-IntuneDeviceSync -WhatIf:$WhatIfPreference)
}
