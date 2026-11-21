#Requires -Version 7.2
<#
.SYNOPSIS
  Records one screen scene of an episode as a live session: opens a clean console window, plays the scene with
  Invoke-LiveScene.ps1 (real commands, real output) and captures that window with ffmpeg to
  <episode>\screens\<name>.mp4, plus a poster frame <name>.jpg. The scene comes from <episode>\record.json.
.EXAMPLE
  .\Record-Scene.ps1 -Episode series\windows-server\episodes\01-windows-server-administration -Screen live-run
#>
param(
    [Parameter(Mandatory)] [string] $Episode,
    [Parameter(Mandatory)] [string] $Screen,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [switch] $SkipPrepare
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RecCommon.ps1')

$epDir = if ([IO.Path]::IsPathRooted($Episode)) { $Episode } else { Join-Path $Root $Episode }
$def = Get-Content -LiteralPath (Join-Path $epDir 'record.json') -Raw | ConvertFrom-Json
$s = $def.screens | Where-Object name -eq $Screen
if (-not $s) { throw "Screen '$Screen' is not in $epDir\record.json" }

if (-not $SkipPrepare -and $s.prepare) {
    Write-Host "Preparing (not recorded): $Screen" -ForegroundColor Yellow
    Invoke-HostStatements -Statements $s.prepare -EpisodeRoot $epDir
}

$ffmpeg = Get-FfmpegPath
$pwsh = (Get-Command pwsh).Source
$id = [guid]::NewGuid().ToString('N').Substring(0, 8)
$windowTitle = "MG-REC $Screen $id"
$markers = Join-Path ([IO.Path]::GetTempPath()) ("mgrec-" + $id)
New-Item -ItemType Directory -Path $markers | Out-Null
$sceneJson = Join-Path $markers 'scene.json'
[ordered]@{
    title = $Screen; windowTitle = $windowTitle; fontSize = $s.fontSize; target = $s.target; workdir = $s.workdir; prompt = $s.prompt; configurationName = $s.configurationName
    commands = @($s.commands); typingDelayMs = $s.typingDelayMs; markerDir = $markers
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $sceneJson -Encoding utf8

$screens = Join-Path $epDir 'screens'
New-Item -ItemType Directory -Force -Path $screens | Out-Null
$mp4 = Join-Path $screens "$Screen.mp4"
$jpg = Join-Path $screens "$Screen.jpg"

# 1. the window to record (classic console host, so the font and size are ours)
$live = Join-Path $PSScriptRoot 'Invoke-LiveScene.ps1'
$p = Start-Process conhost.exe -ArgumentList "`"$pwsh`" -NoProfile -NoLogo -File `"$live`" -SceneFile `"$sceneJson`"" -PassThru
try { $win = Wait-WindowByTitle -Title $windowTitle -TimeoutSeconds 30 }
catch {
    # keep what the scene window left behind, so the reason can be read: recordings\failed-<screen>\
    $keep = Join-Path $Root "recordings\failed-$Screen"
    New-Item -ItemType Directory -Force -Path $keep | Out-Null
    Copy-Item -Path (Join-Path $markers '*') -Destination $keep -Force -ErrorAction SilentlyContinue
    "conhost exited: $($p.HasExited) exit code: $(if ($p.HasExited) { $p.ExitCode })" | Set-Content (Join-Path $keep 'process.txt')
    throw
}
Start-Sleep -Milliseconds 500
Set-RecordingWindow -Handle $win.Handle -Width $(if ($s.width) { $s.width } else { 1600 }) -Height $(if ($s.height) { $s.height } else { 900 })

# 2. capture it
$rec = Start-WindowCapture -Ffmpeg $ffmpeg -Title $win.Title -OutFile $mp4
Write-Host "Recording $Screen -> $mp4" -ForegroundColor Cyan

# 3. wait for the scene to finish, stop the capture, then let the window close
$limit = (Get-Date).AddMinutes($(if ($s.maxMinutes) { $s.maxMinutes } else { 10 }))
while (-not (Test-Path (Join-Path $markers 'done')) -and (Get-Date) -lt $limit -and -not $p.HasExited) { Start-Sleep -Milliseconds 300 }
Start-Sleep -Milliseconds 1200
Stop-WindowCapture $rec
New-Item -ItemType File -Force -Path (Join-Path $markers 'stop') | Out-Null
# wait until the scene window has really closed before the next scene (or kill it), then clean up
if (-not $p.WaitForExit(20000)) { try { $p.Kill($true) } catch {} }

& $ffmpeg -loglevel error -y -sseof -0.5 -i $mp4 -frames:v 1 -update 1 $jpg
# keep the text of what ran on camera next to the clip, so the narration can be checked against the real output
$log = Join-Path $markers 'scene.log'
if (Test-Path $log) { Copy-Item $log ([IO.Path]::ChangeExtension($mp4, '.log')) -Force }
# confidentiality gate: the on-camera text must not show the owner's Windows user name or profile path
if (Test-Path $log) {
    $body = (Get-Content $log -Raw) -split '\*{22}' | Select-Object -Skip 2 | Out-String
    $short = if ($env:USERNAME.Length -gt 6) { $env:USERNAME.Substring(0, 6) + '~' } else { $env:USERNAME }
    $hit = @($env:USERNAME, $env:USERPROFILE, $short) | Where-Object { $_ -and $body -match [regex]::Escape($_) }
    if ($hit) {
        $leakDir = Join-Path (Split-Path $mp4) '_leak'; New-Item -ItemType Directory -Force $leakDir | Out-Null
        Move-Item $mp4, $jpg -Destination $leakDir -Force
        Add-Content (Join-Path $Root 'recordings\leaks.txt') "$(Get-Date -Format s) $mp4"
        throw "Scene shows the Windows user name or profile path; moved to $leakDir. Fix the scene and record it again."
    }
}
Write-Host "Saved $mp4 and poster $jpg" -ForegroundColor Green
Add-RecordingLog -Root $Root -Entry ([ordered]@{ episode = (Resolve-Path $epDir).Path.Substring($Root.Length + 1); screen = $Screen; file = $mp4; at = (Get-Date -Format s) })
Remove-Item -Recurse -Force $markers -ErrorAction SilentlyContinue
