#Requires -Version 7.2
<#
.SYNOPSIS
  DEVLADLOG Windows Server #2 - Active Directory hygiene report.

.DESCRIPTION
  Live (on a DC or a machine with RSAT): exports a snapshot of the domain, saves it as JSON and writes the report.
  Offline: -FromSnapshot re-checks a saved snapshot (how the tests and sample/report.md run on Linux).

.EXAMPLE
  ./Invoke-AdHygieneReport.ps1 -SnapshotFile ./lab-snapshot.json -OutFile ./ad-report.md

.EXAMPLE
  ./Invoke-AdHygieneReport.ps1 -FromSnapshot ../tests/fixtures/lab-snapshot.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md
#>
[CmdletBinding(DefaultParameterSetName = 'Live')]
param(
    [Parameter(ParameterSetName = 'Live')] [string] $Server,
    [Parameter(ParameterSetName = 'Live')] [string] $SnapshotFile,
    [Parameter(ParameterSetName = 'Offline', Mandatory)] [string] $FromSnapshot,
    [string] $PolicyPath = (Join-Path $PSScriptRoot 'policy.json'),
    [string] $OutFile,
    [datetime] $Now = [datetime]::UtcNow,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'AdLab/AdLab.psd1') -Force

$policy = Get-Content -Raw -Path $PolicyPath | ConvertFrom-Json
if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    $snapshot = Get-Content -Raw -Path $FromSnapshot | ConvertFrom-Json
}
else {
    $p = @{}
    if ($Server) { $p.Server = $Server }
    $snapshot = Export-AdLabSnapshot @p
    if ($SnapshotFile) { $snapshot | ConvertTo-Json -Depth 6 | Set-Content -Path $SnapshotFile -Encoding utf8 }
}
if ($snapshot.SchemaVersion -ne 1) { throw "Unsupported snapshot schema version '$($snapshot.SchemaVersion)'." }

$findings = @(Test-AdLabHygiene -Snapshot $snapshot -Policy $policy -Now $Now)
# Out-String -Width: without a console the host width can be 0 and Format-Table prints nothing.
$findings | Format-Table Severity, Check, Object, Detail -AutoSize -Wrap | Out-String -Width 220 | Write-Host
if ($OutFile) {
    ConvertTo-AdLabMarkdown -Finding $findings -Domain $snapshot.Domain.DnsRoot -Now $Now | Set-Content -Path $OutFile -Encoding utf8
    Write-Host "Report written to $OutFile"
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Host ("{0}: {1} finding(s), {2} high." -f $snapshot.Domain.DnsRoot, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
