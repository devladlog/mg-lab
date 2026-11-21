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
$win = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$($cfg.title)*" } | Select-Object -First 1
if (-not $win) { throw "No window with '$($cfg.title)' in its title" }
$title = $win.MainWindowTitle
Write-Host "Recording window: $title -> $out" -ForegroundColor Cyan
New-Item -ItemType File -Force -Path (Join-Path $dir 'recording') | Out-Null
$rec = Start-WindowCapture -Ffmpeg (Get-FfmpegPath) -Title $title -OutFile $out
$end = (Get-Date).AddSeconds($(if ($cfg.maxSeconds) { $cfg.maxSeconds } else { 300 }))
while (-not (Test-Path $stop) -and (Get-Date) -lt $end -and -not $rec.HasExited) { Start-Sleep -Milliseconds 300 }
Stop-WindowCapture $rec
Remove-Item (Join-Path $dir 'recording'), $stop -ErrorAction SilentlyContinue
& (Get-FfmpegPath) -loglevel error -y -sseof -0.5 -i $out -frames:v 1 -update 1 ([IO.Path]::ChangeExtension($out, '.jpg'))
Add-RecordingLog -Root $Root -Entry ([ordered]@{ window = $title; file = $out; at = (Get-Date -Format s) })
Write-Host "Saved $out" -ForegroundColor Green
