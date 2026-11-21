<#
.SYNOPSIS
  DEVLADLOG Windows Server #4 - DNS and DHCP health report.
.DESCRIPTION
  Live: exports a snapshot of the DNS server and every DHCP server named in network.json (DnsServer + DhcpServer
  modules, RSAT) and checks it. Offline: -FromSnapshot re-checks a saved snapshot anywhere.
.EXAMPLE
  ./Invoke-NetLabReport.ps1 -DefinitionPath ./network.json -SnapshotFile ./net-snapshot.json -OutFile ./net-report.md
.EXAMPLE
  ./Invoke-NetLabReport.ps1 -FromSnapshot ../tests/fixtures/net-snapshot.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md
#>
[CmdletBinding(DefaultParameterSetName = 'Live')]
param(
    [string] $DefinitionPath = (Join-Path $PSScriptRoot 'network.json'),
    [Parameter(ParameterSetName = 'Live')][string] $SnapshotFile = './net-snapshot.json',
    [Parameter(ParameterSetName = 'Offline', Mandatory)][string] $FromSnapshot,
    [datetime] $Now = (Get-Date),
    [string] $OutFile,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'NetLab/NetLab.psd1') -Force
$policy = (Get-Content -Raw -Path $DefinitionPath | ConvertFrom-Json).Policy

if ($PSCmdlet.ParameterSetName -eq 'Offline') { $snapshot = Get-Content -Raw -Path $FromSnapshot | ConvertFrom-Json }
else { $snapshot = Export-NetLabSnapshot -DefinitionPath $DefinitionPath -Path $SnapshotFile }

$findings = @(Test-NetLabHealth -Snapshot $snapshot -Policy $policy -Now $Now.ToUniversalTime())
$findings | Format-Table Severity, Check, Target, Detail -Wrap | Out-String -Width 220 | Write-Output
if ($OutFile) { ConvertTo-NetLabMarkdown -Snapshot $snapshot -Finding $findings | Set-Content -Path $OutFile -Encoding UTF8 }
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ("{0}: {1} finding(s), {2} high." -f $snapshot.Dns.ForwardZone, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
