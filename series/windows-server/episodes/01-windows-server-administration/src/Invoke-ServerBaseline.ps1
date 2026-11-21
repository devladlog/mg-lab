#Requires -Version 7.2
<#
.SYNOPSIS
  DEVLADLOG Windows Server #1 - check Windows Servers against a baseline.

.DESCRIPTION
  Live:     collects a snapshot from every server in parallel over PowerShell remoting (WinRM), saves the raw
            snapshots as JSON and writes a findings report.
  Offline:  -FromSnapshot re-evaluates saved JSON snapshots (that's how the tests and the sample report run on Linux).

.EXAMPLE
  ./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-FS01, CON-APP01 -SnapshotDir ./snapshots -OutFile ./report.md

.EXAMPLE
  ./Invoke-ServerBaseline.ps1 -FromSnapshot ../tests/fixtures/*.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md -FailOnHigh
#>
[CmdletBinding(DefaultParameterSetName = 'Live')]
param(
    [Parameter(ParameterSetName = 'Live', Mandatory)] [string[]] $ComputerName,
    [Parameter(ParameterSetName = 'Live')] [pscredential] $Credential,
    [Parameter(ParameterSetName = 'Live')] [string] $SnapshotDir,
    [Parameter(ParameterSetName = 'Offline', Mandatory)] [string[]] $FromSnapshot,
    [string] $BaselinePath = (Join-Path $PSScriptRoot 'baseline.json'),
    [string] $OutFile,
    [datetime] $Now = [datetime]::UtcNow,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ServerBaseline/ServerBaseline.psd1') -Force

$baseline = Get-Content -Raw -Path $BaselinePath | ConvertFrom-Json
$findings = [Collections.Generic.List[object]]::new()
$servers = [Collections.Generic.List[string]]::new()

if ($PSCmdlet.ParameterSetName -eq 'Offline') {
    $files = $FromSnapshot | ForEach-Object { Get-ChildItem -Path $_ -File } | Sort-Object FullName -Unique
    $snapshots = foreach ($f in $files) { Get-Content -Raw -Path $f.FullName | ConvertFrom-Json | ConvertTo-SbSnapshot }
}
else {
    $remoteErrors = $null
    $p = @{ ComputerName = $ComputerName; ErrorAction = 'SilentlyContinue'; ErrorVariable = 'remoteErrors' }
    if ($Credential) { $p.Credential = $Credential }
    $snapshots = @(Get-SbSnapshot @p)
    # Servers we asked for but didn't hear back from become High findings instead of silently disappearing.
    $answered = @($snapshots | ForEach-Object ComputerName)
    foreach ($c in $ComputerName) {
        $short = ($c -split '\.')[0]
        if ($answered -notcontains $short) {
            $err = @($remoteErrors | Where-Object { $_.TargetObject -eq $c -or "$($_.OriginInfo.PSComputerName)" -eq $c }) | Select-Object -First 1
            $reason = if ($err) { ($err.Exception.Message -split "`n")[0].Trim() } else { 'No snapshot returned' }
            $findings.Add((New-SbUnreachableFinding -Server $short -Reason $reason))
            $servers.Add($short)
        }
    }
    if ($SnapshotDir) {
        New-Item -ItemType Directory -Path $SnapshotDir -Force | Out-Null
        foreach ($s in $snapshots) {
            $s | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $SnapshotDir "$($s.ComputerName.ToLowerInvariant()).json")
        }
    }
}

foreach ($s in $snapshots) {
    $servers.Add($s.ComputerName)
    foreach ($f in @(Test-SbBaseline -Snapshot $s -Baseline $baseline -Now $Now)) { $findings.Add($f) }
}

$sorted = @($findings | Format-SbFindingOrder)
# Out-String -Width: without a console (CI, scheduled task) the host width can be 0 and Format-Table prints nothing.
$sorted | Format-Table -Property Severity, Server, Check, Detail -AutoSize -Wrap | Out-String -Width 220 | Write-Host

if ($OutFile) {
    ConvertTo-SbMarkdown -Finding $sorted -Server $servers -Now $Now | Set-Content -Path $OutFile -Encoding utf8
    Write-Host "Report written to $OutFile"
}

$high = @($sorted | Where-Object Severity -eq 'High').Count
Write-Host ("{0} server(s), {1} finding(s), {2} high." -f $servers.Count, $sorted.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
