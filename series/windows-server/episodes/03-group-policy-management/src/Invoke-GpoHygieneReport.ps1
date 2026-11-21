<#
.SYNOPSIS
  DEVLADLOG Windows Server #3 - Group Policy hygiene report.
.DESCRIPTION
  Live: exports a snapshot of the domain's GPOs and links (GroupPolicy + ActiveDirectory modules) and checks it.
  Offline: -FromSnapshot re-checks a saved snapshot anywhere (that's how the tests run on Linux).
.EXAMPLE
  ./Invoke-GpoHygieneReport.ps1 -SnapshotFile ./gpo-snapshot.json -OutFile ./gpo-report.md
.EXAMPLE
  ./Invoke-GpoHygieneReport.ps1 -FromSnapshot ../tests/fixtures/gpo-snapshot.json -OutFile ../sample/report.md -FailOnHigh
#>
[CmdletBinding(DefaultParameterSetName = 'Live')]
param(
    [Parameter(ParameterSetName = 'Live')][string] $SnapshotFile = './gpo-snapshot.json',
    [Parameter(ParameterSetName = 'Live')][string] $Server,
    [Parameter(ParameterSetName = 'Offline', Mandatory)][string] $FromSnapshot,
    [string] $OutFile,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'GpoLab/GpoLab.psd1') -Force

if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    $snapshot = Get-Content -Raw -Path $FromSnapshot | ConvertFrom-Json
}
else {
    $p = @{ Path = $SnapshotFile }
    if ($Server) { $p.Server = $Server }
    $snapshot = Export-GpoLabSnapshot @p
}

$findings = @(Test-GpoLabHygiene -Snapshot $snapshot)
$findings | Format-Table Severity, Check, Target, Detail -Wrap | Out-String -Width 220 | Write-Output
if ($OutFile) {
    ConvertTo-GpoLabMarkdown -Snapshot $snapshot -Finding $findings | Set-Content -Path $OutFile -Encoding UTF8
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ("{0}: {1} GPO(s), {2} finding(s), {3} high." -f $snapshot.Domain, @($snapshot.Gpos).Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
