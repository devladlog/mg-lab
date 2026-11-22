#Requires -Version 7.2
<#
.SYNOPSIS
  Closes the Windows Terminal layout that Start-WtLayout.ps1 opened for one screen: asks each pane to finish, stops
  what is still running in it (process tree: servers, monitors), keeps the pane transcripts next to the take as
  screens\<screen>.<pane>.log and applies the same confidentiality gate as Record-Scene.ps1 (a take whose on-screen
  text shows the Windows user name or profile path is moved to screens\_leak). Safe to run when nothing is open.
  Run from the episode folder:  & ..\..\..\tools\rec\Stop-WtLayout.ps1 -Screen cancel
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Screen,
    [string] $Episode = (Get-Location).Path,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [switch] $Quiet
)
$ErrorActionPreference = 'Stop'
$base = if ($IsWindows) { 'C:\MGLab\wt' } else { Join-Path ([IO.Path]::GetTempPath()) 'mglab-wt' }
$work = Join-Path $base "$(Split-Path $Episode -Leaf)-$Screen"
if (-not (Test-Path $work)) { if (-not $Quiet) { Write-Host "no layout open for $Screen" }; return }

$paneDirs = @(Get-ChildItem -LiteralPath $work -Directory | Sort-Object Name)
foreach ($d in $paneDirs) { New-Item -ItemType File -Force -Path (Join-Path $d.FullName 'stop') | Out-Null }
Start-Sleep -Seconds 2
foreach ($d in $paneDirs) {
    $pidFile = Join-Path $d.FullName 'pid'
    if (-not (Test-Path $pidFile)) { continue }
    $panePid = [int](Get-Content $pidFile -Raw).Trim()
    $proc = Get-Process -Id $panePid -ErrorAction SilentlyContinue
    # same process as the one that wrote the pid file (not a later process that reused the id)
    $same = $proc -and $proc.StartTime -and [math]::Abs(($proc.StartTime - (Get-Item $pidFile).LastWriteTime).TotalSeconds) -lt 120
    if ($same) {
        # the pane is still busy (a server, a monitor): end it with everything it started; the pane then closes
        if ($IsWindows) { taskkill /PID $panePid /T /F 2>&1 | Out-Null } else { try { $proc.Kill($true) } catch {} }
    }
}
Start-Sleep -Milliseconds 800

# transcripts next to the take, then the confidentiality gate
$screens = Join-Path $Episode 'screens'
$mp4 = Join-Path $screens "$Screen.mp4"; $jpg = Join-Path $screens "$Screen.jpg"
$hits = @()
foreach ($d in $paneDirs) {
    $log = Join-Path $d.FullName 'scene.log'
    if (-not (Test-Path $log)) { continue }
    $pane = $d.Name -replace '^\d+-', ''
    if (Test-Path $mp4) { Copy-Item $log (Join-Path $screens "$Screen.$pane.log") -Force }
    $body = (Get-Content $log -Raw) -split '\*{22}' | Select-Object -Skip 2 | Out-String
    $user = [Environment]::UserName
    $short = if ($user.Length -gt 6) { $user.Substring(0, 6) + '~' } else { $user }
    $hits += @($user, [Environment]::GetFolderPath('UserProfile'), $short) | Where-Object { $_ -and $_.Length -gt 2 -and $body -match [regex]::Escape($_) } | ForEach-Object { "$pane" }
}
Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
if ($hits -and (Test-Path $mp4)) {
    $leakDir = Join-Path $screens '_leak'; New-Item -ItemType Directory -Force $leakDir | Out-Null
    Move-Item $mp4, $jpg -Destination $leakDir -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force (Join-Path $Root 'recordings') | Out-Null
    Add-Content (Join-Path $Root 'recordings\leaks.txt') "$(Get-Date -Format s) $mp4"
    throw "Pane(s) $(($hits | Select-Object -Unique) -join ', ') of $Screen show the Windows user name or profile path; take moved to $leakDir. Fix the layout and record it again."
}
if (-not $Quiet) { Write-Host "layout for $Screen closed$(if (Test-Path $mp4) { "; pane transcripts in screens\$Screen.<pane>.log" })" -ForegroundColor Green }
