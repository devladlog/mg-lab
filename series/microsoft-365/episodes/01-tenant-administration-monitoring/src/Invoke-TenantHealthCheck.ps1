#Requires -Version 7.2
<#
.SYNOPSIS
    Read-only Microsoft 365 tenant health check: service health, message center deadlines, licences,
    Global Administrator hygiene, Secure Score trend and inactive licensed users.

.EXAMPLE
    # Live, delegated (an admin signs in; needs the Microsoft.Graph.Authentication module)
    ./Invoke-TenantHealthCheck.ps1 -OutFile ./report.md -SnapshotFile ./snapshot.json

.EXAMPLE
    # App-only, for a scheduled run (certificate in the local store, admin consent granted to the app)
    ./Invoke-TenantHealthCheck.ps1 -TenantId <tenant-id> -ClientId <app-id> -CertificateThumbprint <thumbprint> -FailOnHigh

.EXAMPLE
    # Offline: re-render a saved snapshot (no sign-in at all)
    ./Invoke-TenantHealthCheck.ps1 -FromSnapshot ../tests/fixtures/snapshot.json -Now 2026-11-20 -OutFile ../sample/report.md
#>
[CmdletBinding(DefaultParameterSetName = 'Delegated')]
param(
    [Parameter(ParameterSetName = 'Offline', Mandatory)][string]$FromSnapshot,
    [Parameter(ParameterSetName = 'AppOnly', Mandatory)][string]$TenantId,
    [Parameter(ParameterSetName = 'AppOnly', Mandatory)][string]$ClientId,
    [Parameter(ParameterSetName = 'AppOnly', Mandatory)][string]$CertificateThumbprint,
    [ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D30',
    [int]$InactiveDays = 30,
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow,
    [string]$OutFile,
    [string]$SnapshotFile,
    [string]$TenantLabel = 'contoso',
    [switch]$FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'M365TenantHealth/M365TenantHealth.psd1') -Force

if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    $snapshot = Get-Content -LiteralPath $FromSnapshot -Raw | ConvertFrom-Json
}
else {
    Import-Module Microsoft.Graph.Authentication
    if ($PSCmdlet.ParameterSetName -eq 'AppOnly') {
        Connect-MgGraph -TenantId $TenantId -ClientId $ClientId -CertificateThumbprint $CertificateThumbprint -NoWelcome
    }
    else {
        Connect-MgGraph -Scopes (Get-M365RequiredScope) -NoWelcome
    }
    $snapshot = Get-M365TenantSnapshot -Period $Period
    if ($SnapshotFile) { $snapshot | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $SnapshotFile -Encoding utf8 }
}

$findings = @(Get-M365TenantFinding -Snapshot $snapshot -Now $Now -InactiveDays $InactiveDays)
$findings | Format-Table Severity, Area, Title -AutoSize | Out-String -Width 160 | Out-Host

if ($OutFile) {
    ConvertTo-M365HealthMarkdown -Snapshot $snapshot -Findings $findings -TenantLabel $TenantLabel |
        Set-Content -LiteralPath $OutFile -Encoding utf8
    Write-Information "Report written to $OutFile" -InformationAction Continue
}

$high = @($findings | Where-Object Severity -eq 'High').Count
if ($FailOnHigh -and $high -gt 0) {
    Write-Error "$high high-severity finding(s)." -ErrorAction Continue
    exit 1
}
