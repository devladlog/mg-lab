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

# "prepare: <episode>" / "teardown: <episode>" lines only run that episode's setup or cleanup, for app and browser
# screens that are performed live while Record-Window.ps1 (MG R4) records; nothing is recorded by these lines
# "window-recorder" keeps running and records one window per trigger: write recordings\window.json, then create
# recordings\window.go to start; create recordings\stop to end that take; create recordings\window-recorder.quit to exit.
# This lets app and browser scenes be performed in the app itself, with no trip back to VS Code between takes.
if ($wanted -contains 'window-recorder') {
    $rd = Join-Path $Root 'recordings'
    $state = Join-Path $rd 'window-recorder.state'
    Remove-Item (Join-Path $rd 'window.go'), (Join-Path $rd 'window-recorder.quit') -ErrorAction SilentlyContinue
    Write-Host "Window recorder ready. Waiting for recordings\window.go ..." -ForegroundColor Cyan
    while (-not (Test-Path (Join-Path $rd 'window-recorder.quit'))) {
        Set-Content $state 'idle'
        # recordings\action.txt with "prepare: <episode>" or "teardown: <episode>" runs that step (for the next app episode)
        $actFile = Join-Path $rd 'action.txt'
        if (Test-Path $actFile) {
            $line = (Get-Content $actFile -Raw).Trim(); Remove-Item $actFile
            Set-Content $state 'working'
            try {
                if ($line -notmatch '^(prepare|teardown):\s*(.+)$') { throw "unknown action: $line" }
                $what = $Matches[1]; $epDir = Join-Path $Root ($Matches[2].Trim().Replace('/', '\'))
                $def = Get-Content (Join-Path $epDir 'record.json') -Raw | ConvertFrom-Json
                Write-Host "`n=== $line ===" -ForegroundColor Cyan
                if ($def.$what) { Invoke-HostStatements -Statements $def.$what -EpisodeRoot $epDir }
                Set-Content (Join-Path $rd 'action.last') "ok: $line"
            } catch { Write-Host $_ -ForegroundColor Red; Set-Content (Join-Path $rd 'action.last') "error: $($_.Exception.Message)" }
            continue
        }
        if (Test-Path (Join-Path $rd 'window.go')) {
            Remove-Item (Join-Path $rd 'window.go')
            Set-Content $state 'recording'
            try { & (Join-Path $PSScriptRoot 'Record-Window.ps1') -Root $Root; Set-Content (Join-Path $rd 'window-recorder.last') 'ok' }
            catch { Write-Host $_ -ForegroundColor Red; Set-Content (Join-Path $rd 'window-recorder.last') "error: $($_.Exception.Message)" }
        }
        Start-Sleep -Milliseconds 400
    }
    Set-Content $state 'stopped'
    Remove-Item (Join-Path $rd 'window-recorder.quit') -ErrorAction SilentlyContinue
    Write-Host "Window recorder stopped." -ForegroundColor Green
    return
}

$actions = @($wanted | Where-Object { $_ -match '^(prepare|teardown):\s*(.+)$' })
if ($actions) {
    foreach ($a in $actions) {
        $null = $a -match '^(prepare|teardown):\s*(.+)$'
        $what = $Matches[1]; $epDir = Join-Path $Root ($Matches[2].Trim().Replace('/', '\'))
        $def = Get-Content (Join-Path $epDir 'record.json') -Raw | ConvertFrom-Json
        Write-Host "`n=== $what $($Matches[2].Trim()) ===" -ForegroundColor Cyan
        if ($def.$what) { Invoke-HostStatements -Statements $def.$what -EpisodeRoot $epDir }
        Write-Host "$what done." -ForegroundColor Green
    }
    New-Item -ItemType File -Force -Path (Join-Path $Root 'recordings\queue-actions.done') | Out-Null
    return
}
$episodes = Get-ChildItem (Join-Path $Root 'series\*\episodes\*\record.json') | ForEach-Object { $_.Directory } |
    Where-Object { -not $wanted -or ($wanted -contains $_.FullName.Substring($Root.Length + 1).Replace('/', '\')) -or ($wanted -contains $_.FullName.Substring($Root.Length + 1).Replace('\', '/')) }

$done = 0; $failed = @()
foreach ($ep in $episodes) {
    $def = Get-Content (Join-Path $ep.FullName 'record.json') -Raw | ConvertFrom-Json
    # terminal screens only: browser/app screens are performed live by hand while Record-Window.ps1 (MG R4) records
    $pending = @($def.screens | Where-Object { (-not $_.kind -or $_.kind -eq 'terminal') -and ($Redo -or -not (Test-Path (Join-Path $ep.FullName "screens\$($_.name).mp4"))) })
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
