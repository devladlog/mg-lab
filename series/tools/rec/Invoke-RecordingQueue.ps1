#Requires -Version 7.2
<#
.SYNOPSIS
  Records every pending screen (no .mp4 yet) of the episodes listed in recordings\queue.txt (one episode folder per
  line, relative to the repo root), or of every episode that has a record.json when the file is missing or empty.
  Each episode's "prepare" statements run once before its first screen; its "teardown" statements after its last.
  A line "screen: <episode folder>/<screen name>" records just that one terminal screen (skipped when its .mp4 exists;
  "screen!: ..." records it again). Instead of "prepare"/"teardown" it runs the episode's "prepare_local" and
  "teardown_local" lists (local steps only: no sign-in, prompt, Docker or VM), so screens that need nothing from the
  owner can be recorded even when the episode's own prepare signs in somewhere. Consecutive screen lines of the same
  episode share one prepare_local/teardown_local. Screen lines run first, in queue order; episode lines after them.
  A failure in one line (prepare, recording or teardown) is logged in the failed list and the queue goes on.
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

$screenRe = '^screen(!?):\s*(.+)$'
$screenLines = @($wanted | Where-Object { $_ -match $screenRe })
$actions = @($wanted | Where-Object { $_ -match '^(prepare|teardown):\s*(.+)$' })
if ($actions) {
    if ($screenLines) { Write-Host "Ignored in a prepare:/teardown: queue (put them in their own queue): $($screenLines -join '; ')" -ForegroundColor Yellow }
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
$done = 0; $failed = @()

# --- "screen:" lines: one terminal screen each, with the episode's local-only prepare_local / teardown_local ---------
function Get-ProcessEnvironment {
    $h = @{}
    foreach ($e in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) { $h[[string]$e.Key] = [string]$e.Value }
    $h
}
function Restore-ProcessEnvironment([hashtable] $Saved) {
    # prepare_local may put a venv or a tool folder first on PATH, or set variables: none of it leaks into later lines
    foreach ($k in @([Environment]::GetEnvironmentVariables('Process').Keys)) { if (-not $Saved.ContainsKey([string]$k)) { [Environment]::SetEnvironmentVariable([string]$k, $null, 'Process') } }
    foreach ($k in $Saved.Keys) { if ([Environment]::GetEnvironmentVariable($k, 'Process') -cne $Saved[$k]) { [Environment]::SetEnvironmentVariable($k, $Saved[$k], 'Process') } }
}

$groups = [Collections.Generic.List[object]]::new()
foreach ($l in $screenLines) {
    $null = $l -match $screenRe
    $redo = $Matches[1] -eq '!'
    $spec = $Matches[2].Trim().Replace('\', '/').TrimEnd('/')
    $cut = $spec.LastIndexOf('/')
    if ($cut -lt 1) { $failed += "${l}: expected 'screen: <episode folder>/<screen name>'"; continue }
    $item = [pscustomobject]@{ Episode = $spec.Substring(0, $cut); Screen = $spec.Substring($cut + 1); Redo = $redo }
    $last = if ($groups.Count) { $groups[$groups.Count - 1] } else { $null }
    if ($last -and $last.Episode -eq $item.Episode) { $last.Items.Add($item) }
    else { $g = [pscustomobject]@{ Episode = $item.Episode; Items = [Collections.Generic.List[object]]::new() }; $g.Items.Add($item); $groups.Add($g) }
}
foreach ($g in $groups) {
    $epDir = Join-Path $Root $g.Episode.Replace('/', '\')
    $saved = Get-ProcessEnvironment
    $def = $null; $todo = @(); $prepared = $false; $recorded = @()
    try {
        $def = Get-Content -LiteralPath (Join-Path $epDir 'record.json') -Raw | ConvertFrom-Json
        foreach ($it in $g.Items) {
            $s = $def.screens | Where-Object name -eq $it.Screen
            if (-not $s) { $failed += "$($g.Episode)/$($it.Screen): no such screen in record.json"; continue }
            if ($s.kind -and $s.kind -ne 'terminal') { $failed += "$($g.Episode)/$($it.Screen): $($s.kind) screen (performed live with Record-Window.ps1)"; continue }
            if (-not $it.Redo -and (Test-Path (Join-Path $epDir "screens\$($it.Screen).mp4"))) { Write-Host "skip $($g.Episode)/$($it.Screen): already recorded (screen!: records it again)"; continue }
            $todo += $it
        }
        if ($todo) {
            Write-Host "`n=== $($g.Episode): $($todo.Count) screen(s), prepare_local ===" -ForegroundColor Cyan
            $prepared = $true
            if ($def.prepare_local) { Invoke-HostStatements -Statements $def.prepare_local -EpisodeRoot $epDir }
            foreach ($it in $todo) {
                $recorded += $it
                try { & (Join-Path $PSScriptRoot 'Record-Scene.ps1') -Episode $epDir -Screen $it.Screen -Root $Root; $done++ }
                catch { $failed += "$($g.Episode)/$($it.Screen): $($_.Exception.Message)"; Write-Host $_ -ForegroundColor Red }
            }
        }
    } catch {
        # record.json or prepare_local failed: the screens not tried yet are not recorded; the next line still runs
        $err = $_
        foreach ($it in @($todo | Where-Object { $recorded -notcontains $_ })) { $failed += "$($g.Episode)/$($it.Screen): not recorded, prepare_local: $($err.Exception.Message)" }
        if (-not $todo) { $failed += "$($g.Episode): $($err.Exception.Message)" }
        Write-Host $err -ForegroundColor Red
    } finally {
        if ($prepared -and $def.teardown_local) {
            try { Invoke-HostStatements -Statements $def.teardown_local -EpisodeRoot $epDir }
            catch { $failed += "$($g.Episode): teardown_local: $($_.Exception.Message)"; Write-Host "teardown_local: $_" -ForegroundColor Red }
        }
        Restore-ProcessEnvironment $saved
    }
}

# --- episode lines (or every episode with a record.json when the queue has no lines at all) -------------------------
$episodeLines = @($wanted | Where-Object { $_ -notmatch $screenRe })
$episodes = if ($screenLines -and -not $episodeLines) { @() } else {
    Get-ChildItem (Join-Path $Root 'series\*\episodes\*\record.json') | ForEach-Object { $_.Directory } |
        Where-Object { -not $episodeLines -or ($episodeLines -contains $_.FullName.Substring($Root.Length + 1).Replace('/', '\')) -or ($episodeLines -contains $_.FullName.Substring($Root.Length + 1).Replace('\', '/')) }
}

foreach ($ep in $episodes) {
    try { $def = Get-Content (Join-Path $ep.FullName 'record.json') -Raw | ConvertFrom-Json }
    catch { $failed += "$($ep.Name): record.json: $($_.Exception.Message)"; Write-Host $_ -ForegroundColor Red; continue }
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
    } catch {
        # the episode's prepare threw: its screens are not recorded, and the queue goes on with the next episode
        $failed += "$($ep.Name): prepare failed, $($pending.Count) screen(s) not recorded: $($_.Exception.Message)"
        Write-Host "prepare: $_" -ForegroundColor Red
    } finally {
        if ($def.teardown) { try { Invoke-HostStatements -Statements $def.teardown -EpisodeRoot $ep.FullName } catch { Write-Host "teardown: $_" -ForegroundColor Red } }
    }
}
Write-Host "`nRecorded $done screen(s)." -ForegroundColor Green
if ($failed) { Write-Host "Failed:`n  $($failed -join "`n  ")" -ForegroundColor Red; exit 1 }
