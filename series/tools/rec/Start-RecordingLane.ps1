#Requires -Version 7.2
<#
.SYNOPSIS
  Starts one more recorder loop (a "lane") in its own minimized console, next to the main one (VS Code task MG R2).
  A lane takes the same action lines as the main loop, from recordings\lane-<name>\action.txt, answers in
  recordings\lane-<name>\action.last and records terminal screens only, in a window placed at -X/-Y (physical pixels).
  Lanes whose windows do not overlap can record at the same time; app and browser takes stay with the main loop.
  Its log is recordings\lane-<name>\transcript.txt. Stop it: create recordings\lane-<name>\window-recorder.quit.
  Does nothing when that lane is already running.
.EXAMPLE
  .\Start-RecordingLane.ps1 -Lane b -X 1960 -Y 40      # second display
#>
param(
    [Parameter(Mandatory)] [ValidatePattern('^[a-z0-9]+$')] [string] $Lane,
    [int] $X = 40, [int] $Y = 40,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
)
$ErrorActionPreference = 'Stop'
$rd = Join-Path $Root "recordings\lane-$Lane"
New-Item -ItemType Directory -Force -Path $rd | Out-Null
$pidFile = Join-Path $rd 'lane.pid'
if (Test-Path $pidFile) {
    $old = Get-Process -Id ([int]"$(Get-Content $pidFile -Raw)".Trim()) -ErrorAction SilentlyContinue
    if ($old -and $old.ProcessName -eq 'pwsh') { Write-Host "Lane $Lane is already running (process $($old.Id))."; return }
}
Remove-Item (Join-Path $rd 'window-recorder.quit'), (Join-Path $rd 'action.txt') -ErrorAction SilentlyContinue
$pwsh = (Get-Command pwsh -CommandType Application | Select-Object -First 1).Source
$loop = Join-Path $PSScriptRoot 'Invoke-RecordingQueue.ps1'
$log = Join-Path $rd 'transcript.txt'
# the paths hold no quote characters; the whole -Command text travels as one double-quoted argument
$cmd = "Start-Transcript '$log' -Force | Out-Null; try { & '$loop' -Lane '$Lane' -X $X -Y $Y } finally { Stop-Transcript | Out-Null }"
$state = Join-Path $rd 'window-recorder.state'
Remove-Item $state -ErrorAction SilentlyContinue
$p = Start-Process conhost.exe -WindowStyle Minimized -WorkingDirectory $Root -PassThru `
    -ArgumentList "`"$pwsh`" -NoProfile -NoLogo -ExecutionPolicy Bypass -Command `"$cmd`""
# wait until the loop itself says it is ready (its state file), at most 30 s
$end = (Get-Date).AddSeconds(30)
while (-not (Test-Path $state) -and (Get-Date) -lt $end -and -not $p.HasExited) { Start-Sleep -Milliseconds 300 }
if (-not (Test-Path $state)) { throw "Lane $Lane did not start (see $log)" }
Write-Host "Lane $Lane started: terminal screens at $X,$Y; actions in recordings\lane-$Lane\action.txt" -ForegroundColor Green
