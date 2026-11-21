#Requires -Version 7.2
<#
.SYNOPSIS
  Records one window (a browser or desktop app) while a scene is performed live, for browser/app screens.
  Reads recordings\window.json: { "title": "<part of the window title>", "out": "<episode>\\screens\\<name>.mp4",
  "maxSeconds": 300 }. Recording stops when recordings\stop appears (or after maxSeconds); a poster .jpg is saved
  next to the .mp4. Started from the VS Code task "MG R4".
#>
param([string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RecCommon.ps1')
$dir = Join-Path $Root 'recordings'
$cfg = Get-Content (Join-Path $dir 'window.json') -Raw | ConvertFrom-Json
$stop = Join-Path $dir 'stop'
Remove-Item $stop -ErrorAction SilentlyContinue
$out = if ([IO.Path]::IsPathRooted($cfg.out)) { $cfg.out } else { Join-Path $Root $cfg.out }
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

# find the full title of the first visible window whose title contains the text
$win = Wait-WindowByTitle -Title $cfg.title -TimeoutSeconds 10
$title = $win.Title
# same framing as the terminal scenes: top-most so nothing covers it, fixed size (window.json width/height override)
$w = if ($cfg.width) { [int]$cfg.width } else { 1600 }; $h = if ($cfg.height) { [int]$cfg.height } else { 900 }
Set-RecordingWindow -Handle $win.Handle -Width $w -Height $h
Start-Sleep -Milliseconds 800
Write-Host "Recording window: $title -> $out" -ForegroundColor Cyan
New-Item -ItemType File -Force -Path (Join-Path $dir 'recording') | Out-Null
$rec = Start-WindowCapture -Ffmpeg (Get-FfmpegPath) -Title $title -OutFile $out -DrawMouse
$end = (Get-Date).AddSeconds($(if ($cfg.maxSeconds) { $cfg.maxSeconds } else { 300 }))
try {
    while (-not (Test-Path $stop) -and (Get-Date) -lt $end -and -not $rec.HasExited) { Start-Sleep -Milliseconds 300 }
} finally {
    Stop-WindowCapture $rec
    [void][MgRec.Win2]::SetWindowPos($win.Handle, [IntPtr]::new(-2), 0, 0, 0, 0, 0x0003)   # no longer top-most
}
Remove-Item (Join-Path $dir 'recording'), $stop -ErrorAction SilentlyContinue
& (Get-FfmpegPath) -loglevel error -y -sseof -0.5 -i $out -frames:v 1 -update 1 ([IO.Path]::ChangeExtension($out, '.jpg'))
Add-RecordingLog -Root $Root -Entry ([ordered]@{ window = $title; file = $out; at = (Get-Date -Format s) })
Write-Host "Saved $out" -ForegroundColor Green
