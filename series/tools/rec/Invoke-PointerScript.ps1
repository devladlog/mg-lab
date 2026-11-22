#Requires -Version 7.2
<#
.SYNOPSIS
  Plays a short pointer choreography (moves and left clicks only, never the keyboard) inside ONE window while the
  window recorder captures it, so a click-only app take runs by itself: same result every time, and nothing but the
  app is on screen (no remote-control overlay, no pause between steps).

.DESCRIPTION
  Reads the screen's "pointer" list and "window.title" from <episode>\record.json:
    "pointer": [ { "wait": 2 }, { "click": [92, 1007] }, { "wait": 3 }, { "move": [692, 484] }, { "wait": 6 },
                 { "move": [1398, 628] }, { "wait": 1.5 } ]
  - Coordinates are physical pixels from the top-left corner of the recorded frame (the window's visible bounds:
    the same pixels as the recorded .mp4), so they can be measured on a frame of an earlier take.
  - Every point must lie inside the window; a point outside stops the script before anything moves.
  - "move" glides the pointer there (hover), "click" glides there and presses the left button once,
    "wait" pauses (seconds). An optional "glide" (seconds, default 0.5) on a move or click sets the travel time.
  The script waits for recordings\recording (created when Record-Window.ps1 starts capturing), plays the steps and
  creates recordings\stop, which ends the take. It writes what it did to recordings\pointer.log.

  -Start      launches the script hidden in the background and returns at once ("screen-play:" action), so the
              recorder is free to start the take.
  -Check      validates the steps against the window size from "window" (width/height) without moving anything
              (works on Linux too).
  -CloseWindow asks the screen's window to close (WM_CLOSE), for the screen teardown. Nothing is forced.
  Run from the episode folder:  & ..\..\..\tools\rec\Invoke-PointerScript.ps1 -Screen editor-never -Start
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Screen,
    [string] $Episode = (Get-Location).Path,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [switch] $Start,
    [switch] $Check,
    [switch] $CloseWindow,
    [int] $TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'

$def = Get-Content -LiteralPath (Join-Path $Episode 'record.json') -Raw | ConvertFrom-Json
$s = $def.screens | Where-Object name -eq $Screen
if (-not $s) { throw "Screen '$Screen' is not in $Episode\record.json" }
if (-not $s.window -or -not $s.window.title) { throw "Screen '$Screen' needs window.title" }
$title = "$($s.window.title)"

if ($CloseWindow) {
    if (-not $IsWindows) { throw 'Windows only' }
    . (Join-Path $PSScriptRoot 'RecCommon.ps1')
    try { $win = Wait-WindowByTitle -Title $title -TimeoutSeconds 3 } catch { Write-Host "no window titled '*$title*' (already closed)"; return }
    Add-Type -Namespace MgRec -Name PtrClose -MemberDefinition '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr w, IntPtr l);'
    [void][MgRec.PtrClose]::PostMessage($win.Handle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)   # WM_CLOSE
    Write-Host "asked '$($win.Title)' to close"
    return
}

$steps = @($s.pointer | Where-Object { $_ })
if (-not $steps.Count) { throw "Screen '$Screen' has no pointer steps" }
function Get-Point($step) {
    foreach ($k in 'move', 'click') {
        if ($step.PSObject.Properties[$k]) {
            $p = @($step.$k)
            if ($p.Count -ne 2) { throw "pointer step '$k' needs [x, y]" }
            return [pscustomobject]@{ Kind = $k; X = [int]$p[0]; Y = [int]$p[1] }
        }
    }
    $null
}
foreach ($st in $steps) {
    $names = @($st.PSObject.Properties.Name | Where-Object { $_ -ne 'glide' })
    if ($names.Count -ne 1 -or $names[0] -notin 'wait', 'move', 'click') { throw "pointer step must be one of wait, move, click (optionally with glide): $($st | ConvertTo-Json -Compress)" }
    if ($names[0] -eq 'wait' -and ([double]$st.wait -lt 0 -or [double]$st.wait -gt 120)) { throw "pointer wait must be 0..120 s" }
}
if ($Check) {
    $w = if ($s.window.width) { [int]$s.window.width } else { 1920 }; $h = if ($s.window.height) { [int]$s.window.height } else { 1080 }
    foreach ($st in $steps) { $p = Get-Point $st; if ($p -and ($p.X -lt 0 -or $p.Y -lt 0 -or $p.X -ge $w -or $p.Y -ge $h)) { throw "pointer $($p.Kind) [$($p.X), $($p.Y)] is outside the ${w}x$h window" } }
    Write-Host "pointer script for $Screen OK: $($steps.Count) steps, window '*$title*'" -ForegroundColor Green
    return
}
if (-not $IsWindows) { throw 'Invoke-PointerScript moves the pointer on the recording laptop: Windows only (use -Check elsewhere)' }

if ($Start) {
    $pwsh = (Get-Command pwsh -CommandType Application | Select-Object -First 1).Source
    Start-Process -FilePath $pwsh -WindowStyle Hidden -ArgumentList @('-NoProfile', '-NoLogo', '-File', "`"$PSCommandPath`"", '-Screen', $Screen, '-Episode', "`"$Episode`"", '-Root', "`"$Root`"", '-TimeoutSeconds', $TimeoutSeconds) | Out-Null
    Write-Host "pointer script for $Screen waits for the take ($($steps.Count) steps)" -ForegroundColor Green
    return
}

. (Join-Path $PSScriptRoot 'RecCommon.ps1')
Add-Type -Namespace MgRec -Name Ptr -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr ctx);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
[DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
'@
[void][MgRec.Ptr]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))   # physical pixels, like Record-Window.ps1

$recDir = Join-Path $Root 'recordings'
$log = Join-Path $recDir 'pointer.log'
function Write-Log([string] $m) { Add-Content -LiteralPath $log -Value ("{0:HH:mm:ss.fff} {1}" -f (Get-Date), $m) }
Set-Content -LiteralPath $log -Value "pointer script: $Episode / $Screen"
try {
    $marker = Join-Path $recDir 'recording'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-Path $marker)) { if ((Get-Date) -gt $deadline) { throw "no take started within $TimeoutSeconds s" }; Start-Sleep -Milliseconds 100 }
    $win = Wait-WindowByTitle -Title $title -TimeoutSeconds 10
    $b = Get-WindowBounds $win.Handle   # x, y, width, height of the recorded region
    Write-Log "take started; window '$($win.Title)' at [$($b -join ',')]"
    foreach ($st in $steps) { $p = Get-Point $st; if ($p -and ($p.X -lt 0 -or $p.Y -lt 0 -or $p.X -ge $b[2] -or $p.Y -ge $b[3])) { throw "pointer $($p.Kind) [$($p.X), $($p.Y)] is outside the window ($($b[2])x$($b[3]))" } }

    function Move-Glide([int] $x, [int] $y, [double] $seconds) {
        $from = [MgRec.Ptr+POINT]::new(); [void][MgRec.Ptr]::GetCursorPos([ref]$from)
        $n = [Math]::Max(1, [int]($seconds * 60))
        for ($i = 1; $i -le $n; $i++) {
            $t = $i / $n; $e = $t * $t * (3 - 2 * $t)   # ease in and out
            [void][MgRec.Ptr]::SetCursorPos([int]($from.X + ($x - $from.X) * $e), [int]($from.Y + ($y - $from.Y) * $e))
            Start-Sleep -Milliseconds 16
        }
        [void][MgRec.Ptr]::SetCursorPos($x, $y)
        # one more small move so the app sees a fresh mouse-move at the final position (hover timers start here)
        [MgRec.Ptr]::mouse_event(0x0001, 1, 0, 0, [UIntPtr]::Zero); [MgRec.Ptr]::mouse_event(0x0001, [uint32]::MaxValue, 0, 0, [UIntPtr]::Zero)
    }
    foreach ($st in $steps) {
        if (Test-Path (Join-Path $recDir 'stop')) { Write-Log 'take was stopped from outside'; break }
        if ($st.PSObject.Properties['wait']) { Start-Sleep -Milliseconds ([int]([double]$st.wait * 1000)); continue }
        $p = Get-Point $st
        $glide = if ($st.PSObject.Properties['glide']) { [double]$st.glide } else { 0.5 }
        Move-Glide ($b[0] + $p.X) ($b[1] + $p.Y) $glide
        if ($p.Kind -eq 'click') {
            Start-Sleep -Milliseconds 150
            [MgRec.Ptr]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60; [MgRec.Ptr]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        }
        Write-Log "$($p.Kind) [$($p.X), $($p.Y)]"
    }
    Write-Log 'done'
} catch { Write-Log "ERROR: $($_.Exception.Message)" }
finally { New-Item -ItemType File -Force -Path (Join-Path $recDir 'stop') | Out-Null }
