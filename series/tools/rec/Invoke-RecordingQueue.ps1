#Requires -Version 7.2
<#
.SYNOPSIS
  Records every pending screen (no .mp4 yet) of the episodes listed in recordings\queue.txt (one episode folder per
  line, relative to the repo root), or of every episode that has a record.json when the file is missing or empty.
  Each episode's "prepare" statements run once before its first screen; its "teardown" statements after its last.
#>
param([string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path, [switch] $Redo)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RecCommon.ps1')

$queueFile = Join-Path $Root 'recordings\queue.txt'
$wanted = if (Test-Path $queueFile) { @(Get-Content $queueFile | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') }) } else { @() }
$episodes = Get-ChildItem (Join-Path $Root 'series\*\episodes\*\record.json') | ForEach-Object { $_.Directory } |
    Where-Object { -not $wanted -or ($wanted -contains $_.FullName.Substring($Root.Length + 1).Replace('/', '\')) -or ($wanted -contains $_.FullName.Substring($Root.Length + 1).Replace('\', '/')) }

$done = 0; $failed = @()
foreach ($ep in $episodes) {
    $def = Get-Content (Join-Path $ep.FullName 'record.json') -Raw | ConvertFrom-Json
    $pending = @($def.screens | Where-Object { $Redo -or -not (Test-Path (Join-Path $ep.FullName "screens\$($_.name).mp4")) })
    if (-not $pending) { continue }
    Write-Host "`n=== $($ep.Parent.Parent.Name)/$($ep.Name): $($pending.Count) screen(s) ===" -ForegroundColor Cyan
    try {
        if ($def.prepare) { Invoke-HostStatements -Statements $def.prepare -EpisodeRoot $ep.FullName }
        foreach ($s in $pending) {
            try { & (Join-Path $PSScriptRoot 'Record-Scene.ps1') -Episode $ep.FullName -Screen $s.name -Root $Root; $done++ }
            catch { $failed += "$($ep.Name)/$($s.name): $($_.Exception.Message)"; Write-Host $_ -ForegroundColor Red }
        }
    } finally {
        if ($def.teardown) { try { Invoke-HostStatements -Statements $def.teardown -EpisodeRoot $ep.FullName } catch { Write-Host "teardown: $_" -ForegroundColor Red } }
    }
}
Write-Host "`nRecorded $done screen(s)." -ForegroundColor Green
if ($failed) { Write-Host "Failed:`n  $($failed -join "`n  ")" -ForegroundColor Red; exit 1 }
