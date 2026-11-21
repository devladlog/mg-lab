<#
.SYNOPSIS
Measures what clients really see while a clustered role fails over: requests the role's URL every 500 ms and reports outages.
.EXAMPLE
./Watch-ClusterRole.ps1 -DurationSec 90 -OutFile ./probe.jsonl      # start it, then run Deploy-ClusterLab.ps1 -Step Drain on a node
.EXAMPLE
./Watch-ClusterRole.ps1 -FromFile ../tests/fixtures/probe-drain.jsonl        # summarise a saved run
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'cluster-lab.json'),
    [string] $Url,
    [int] $DurationSec = 60,
    [int] $IntervalMs = 500,
    [string] $OutFile,
    [string] $FromFile
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ClusterLab/ClusterLab.psd1') -Force
if ($FromFile) { $samples = @(Get-Content -LiteralPath $FromFile | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }) }
else {
    if (-not $Url) { $Url = [string](Read-ClfLabConfig -Path $ConfigPath).Role.Url }
    if ($OutFile -and (Test-Path -LiteralPath $OutFile)) { Remove-Item -LiteralPath $OutFile }
    $samples = @(Invoke-ClfProbe -Url $Url -DurationSec $DurationSec -IntervalMs $IntervalMs -OutFile $OutFile)
}
$sum = Get-ClfProbeSummary -Samples $samples
'Samples: {0}   failed: {1}   server changes: {2}' -f $sum.Samples, $sum.Failed, $sum.ServerChanges
$sum.ServedBy.GetEnumerator() | ForEach-Object { 'Served by {0}: {1} request(s)' -f $_.Key, $_.Value }
$sum.Outages | Format-Table Start, End, Seconds, FailedRequests | Out-String -Width 200 | Write-Output
'Outages: {0}   longest: {1} s   total downtime: {2} s' -f $sum.OutageCount, $sum.LongestOutageSeconds, $sum.TotalDowntimeSeconds
