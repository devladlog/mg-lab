#Requires -Version 7.2
<#
.SYNOPSIS
  Opens a new Windows Terminal window with split panes for one app screen, each pane playing a live scene
  (Invoke-LiveScene.ps1: commands typed and run for real), so a two-pane terminal take needs no typing by hand.

.DESCRIPTION
  Reads the screen's "layout" from <episode>\record.json:
    "layout": {
      "title": "MG pl03",                      // every pane's tab title ends with it: use it as window.json "title"
      "panes": [                               // left to right (vertical splits)
        { "title": "api", "workdir": "C:\\lab\\pl03", "prompt": "> ", "commands": ["dotnet run ..."] },
        { "title": "client", "workdir": "C:\\lab\\pl03", "prompt": "> ", "size": 0.5, "commands": ["..."] }
      ],
      "requires": ["dotnet-counters"],         // optional: commands that must be on the PATH a new terminal gets
      "fontSize": 14,                          // optional (default 14)
      "stopPane": "client"                     // optional: pane whose end stops the take (default: the last pane)
    }
  Every pane first waits for the window recorder's recordings\recording marker (created when Record-Window.ps1
  starts capturing), so nothing happens on screen before the take starts; then it plays its commands (hidden
  directives #pause/#waitport/#raw etc., see Invoke-LiveScene.ps1). When the stop pane has played its last command it
  creates recordings\stop, which ends the take. Panes stay open until Stop-WtLayout.ps1 closes them.
  The panes use a Windows Terminal profile "MG Lab Rec" (font size, dark scheme, no scrollbar, title fixed by us),
  written as a settings fragment under %LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\MGLab.
  Run from the episode folder (screen prepare statements do):  & ..\..\..\tools\rec\Start-WtLayout.ps1 -Screen cancel
  -Check validates the layout and prints the wt.exe command line without starting anything (works on Linux too).
  -Simulate plays the panes as plain background pwsh processes instead of Windows Terminal panes (no window to
  record): a dry run of the whole take, e.g. in the build container with -Workdir pointing at a copy of the episode.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Screen,
    [string] $Episode = (Get-Location).Path,
    [string] $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [switch] $Check,
    [switch] $Simulate,
    [string] $Workdir   # -Simulate only: run every pane in this folder instead of its layout workdir
)
$ErrorActionPreference = 'Stop'

$def = Get-Content -LiteralPath (Join-Path $Episode 'record.json') -Raw | ConvertFrom-Json
$s = $def.screens | Where-Object name -eq $Screen
if (-not $s) { throw "Screen '$Screen' is not in $Episode\record.json" }
$layout = $s.layout
if (-not $layout) { throw "Screen '$Screen' has no layout" }
if (-not $layout.title) { throw "layout.title is missing" }
$panes = @($layout.panes)
if ($panes.Count -lt 2) { throw "layout.panes needs at least two panes" }
foreach ($p in $panes) {
    if (-not $p.title -or -not $p.workdir -or -not @($p.commands).Count) { throw "every pane needs title, workdir and commands[]" }
}
$stopPane = if ($layout.stopPane) { "$($layout.stopPane)" } else { "$($panes[-1].title)" }
if (-not ($panes | Where-Object title -eq $stopPane)) { throw "layout.stopPane '$stopPane' is not a pane title" }
$fontSize = if ($layout.fontSize) { [int]$layout.fontSize } else { 14 }
$profileName = 'MG Lab Rec'

$recDir = Join-Path $Root 'recordings'
$startMarker = Join-Path $recDir 'recording'
$stopMarker = Join-Path $recDir 'stop'
$base = if ($IsWindows) { 'C:\MGLab\wt' } else { Join-Path ([IO.Path]::GetTempPath()) 'mglab-wt' }
$name = "$(Split-Path $Episode -Leaf)-$Screen"
$work = Join-Path $base $name
$live = Join-Path $PSScriptRoot 'Invoke-LiveScene.ps1'

# close an earlier copy of this layout (idempotent prepare)
if (-not $Check -and (Test-Path $work)) { & (Join-Path $PSScriptRoot 'Stop-WtLayout.ps1') -Screen $Screen -Episode $Episode -Root $Root -Quiet }

# one scene file per pane, as Record-Scene.ps1 writes them for conhost scenes
$paneArgs = @()
$i = 0
foreach ($p in $panes) {
    $i++
    $dir = Join-Path $work ("{0}-{1}" -f $i, ($p.title -replace '[^\w.-]', '_'))
    $title = "$($p.title) | $($layout.title)"
    $cmds = @("#waitfile $startMarker 1800", '#pause 2') + @($p.commands)
    if ($p.title -eq $stopPane) { $cmds += @('#pause 1', "#touch $stopMarker") }
    $scene = [ordered]@{
        title = $p.title; windowTitle = $title; target = 'host'; workdir = $(if ($Simulate -and $Workdir) { $Workdir } else { $p.workdir })
        prompt = $(if ($p.prompt) { $p.prompt } else { '> ' }); commands = $cmds
        typingDelayMs = $p.typingDelayMs; markerDir = $dir; keepOpen = $true
        # panes start with the registry PATH; carry the recorder's PATH (node, dotnet tools set up by the prepare)
        path = $env:PATH
    }
    $sceneFile = Join-Path $dir 'scene.json'
    if (-not $Check) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $scene | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $sceneFile -Encoding utf8
    }
    $paneArgs += [pscustomobject]@{ Title = $title; Workdir = $p.workdir; SceneFile = $sceneFile; Size = $p.size; Commands = $cmds }
}

function Get-RegistryPathDirs {
    # the PATH a brand-new terminal gets (Windows Terminal starts panes with a fresh environment from the registry)
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine'); $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    @("$m;$u" -split ';' | Where-Object { $_ } | ForEach-Object { [Environment]::ExpandEnvironmentVariables($_) })
}
$missing = @()
foreach ($req in @($layout.requires)) {
    if (-not $req) { continue }
    if ($IsWindows) {
        $hit = Get-RegistryPathDirs | Where-Object { foreach ($ext in '.exe', '.cmd', '.bat', '.ps1') { if (Test-Path -LiteralPath (Join-Path $_ "$req$ext")) { return $true } }; $false }
        if (-not $hit) { $missing += $req }
    } elseif (-not (Get-Command $req -ErrorAction SilentlyContinue)) { $missing += "$req (not on this machine's PATH)" }
}

$pwshExe = if ($IsWindows) { (Get-Command pwsh -CommandType Application | Select-Object -First 1).Source } else { 'pwsh.exe' }
function Format-Arg([string] $a) { if ($a -match '[\s;"]') { '"' + $a + '"' } else { $a } }
$parts = @('-w', 'new')
$j = 0
foreach ($pa in $paneArgs) {
    if ($j -gt 0) { $parts += ';'; $parts += 'split-pane', '-V'; $parts += '-s', ([double]$(if ($pa.Size) { $pa.Size } else { 1.0 / ($paneArgs.Count - $j + 1) })).ToString('0.##', [Globalization.CultureInfo]::InvariantCulture) }
    else { $parts += 'new-tab' }
    $parts += '--title', (Format-Arg $pa.Title), '--suppressApplicationTitle', '-p', (Format-Arg $profileName), '-d', (Format-Arg $pa.Workdir)
    $parts += (Format-Arg $pwshExe), '-NoProfile', '-NoLogo', '-File', (Format-Arg $live), '-SceneFile', (Format-Arg $pa.SceneFile)
    $j++
}
$wtArgs = $parts -join ' '

if ($Check) {
    Write-Host "layout '$($layout.title)' for $Screen OK: $($paneArgs.Count) panes, stop pane '$stopPane', font $fontSize" -ForegroundColor Green
    foreach ($pa in $paneArgs) { Write-Host "  [$($pa.Title)] $($pa.Workdir)"; $pa.Commands | ForEach-Object { Write-Host "      $_" } }
    if ($missing) { Write-Host "  requires missing: $($missing -join ', ')" -ForegroundColor Yellow }
    Write-Host "  wt.exe $wtArgs" -ForegroundColor DarkGray
    return
}

if ($Simulate) {
    foreach ($pa in $paneArgs) {
        $sp = @{ FilePath = (Get-Command pwsh -CommandType Application | Select-Object -First 1).Source; ArgumentList = @('-NoProfile', '-NoLogo', '-File', (Format-Arg $live), '-SceneFile', (Format-Arg $pa.SceneFile)) }
        if ($IsWindows) { $sp.WindowStyle = 'Hidden' } else { $sp.RedirectStandardOutput = Join-Path (Split-Path $pa.SceneFile) 'console.txt'; $sp.RedirectStandardInput = '/dev/null' }
        Start-Process @sp | Out-Null
    }
    Write-Host "Simulated layout '$($layout.title)': $($paneArgs.Count) pane processes wait for $startMarker" -ForegroundColor Green
    return
}
if (-not $IsWindows) { throw 'Start-WtLayout opens Windows Terminal: Windows only (use -Check or -Simulate elsewhere)' }
if ($missing) { throw "Not on the PATH of a new terminal: $($missing -join ', ') (a pane would fail on camera)" }
$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $wt) { throw 'wt.exe (Windows Terminal) not found: winget install --id Microsoft.WindowsTerminal -e' }
foreach ($pa in $paneArgs) { if (-not (Test-Path -LiteralPath $pa.Workdir)) { throw "pane folder $($pa.Workdir) does not exist (run the episode prepare first)" } }

# the recording profile, as a settings fragment (no edit of the owner's settings.json)
$fragDir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\Fragments\MGLab'
$frag = [ordered]@{
    profiles = @([ordered]@{
            name = $profileName; commandline = "pwsh.exe -NoProfile -NoLogo"; hidden = $false
            font = [ordered]@{ face = 'Cascadia Mono'; size = $fontSize }; colorScheme = 'Campbell'; background = '#0C0C0C'
            padding = '10'; scrollbarState = 'hidden'; closeOnExit = 'always'; suppressApplicationTitle = $true
            bellStyle = 'none'; cursorShape = 'bar'; antialiasingMode = 'cleartype'; useAcrylic = $false; opacity = 100
        })
} | ConvertTo-Json -Depth 5
$fragFile = Join-Path $fragDir 'mglab-rec.json'
$changed = -not (Test-Path $fragFile) -or ((Get-Content $fragFile -Raw) -ne $frag)
if ($changed) {
    New-Item -ItemType Directory -Force -Path $fragDir | Out-Null
    Set-Content -LiteralPath $fragFile -Value $frag -Encoding utf8 -NoNewline
    if (Get-Process WindowsTerminal -ErrorAction SilentlyContinue) {
        # a running Windows Terminal reads fragments when its settings reload: nudge it by touching settings.json
        $settings = @("$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
            "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
            "$env:LOCALAPPDATA\Microsoft\Windows Terminal\settings.json") | Where-Object { Test-Path -LiteralPath $_ }
        foreach ($f in $settings) { (Get-Item -LiteralPath $f).LastWriteTime = Get-Date }
        Write-Host "  profile '$profileName' written; Windows Terminal is running: if the panes open with another font, close every Windows Terminal window and run this screen's prepare again" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

# a marker left by an interrupted take would start the panes at once
$state = Join-Path $recDir 'window-recorder.state'
if ((Test-Path $startMarker) -and -not ((Test-Path $state) -and (Get-Content $state -Raw).Trim() -eq 'recording')) { Remove-Item $startMarker -Force }

Start-Process -FilePath $wt.Source -ArgumentList $wtArgs | Out-Null
$deadline = (Get-Date).AddSeconds(30)
foreach ($pa in $paneArgs) {
    $started = Join-Path (Split-Path $pa.SceneFile) 'started'
    while (-not (Test-Path $started) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
    if (-not (Test-Path $started)) { throw "pane '$($pa.Title)' did not start within 30 s (see $(Split-Path $pa.SceneFile))" }
}
. (Join-Path $PSScriptRoot 'RecCommon.ps1')
$win = Wait-WindowByTitle -Title $layout.title -TimeoutSeconds 15
Write-Host "Windows Terminal layout ready: '$($win.Title)'. Panes wait for the take; window.json title: '$($layout.title)'" -ForegroundColor Green
