#Requires -Version 7.2
<#
.SYNOPSIS
  Opens VS Code for one app screen, ready to record with clicks and hovers only: writes the folder's
  .vscode\settings.json (dark theme, large fonts, zoom, fixed window title, no accounts badge, no AI chrome) and,
  if given, .vscode\tasks.json (commands the lead runs from Terminal > Run Task...), then opens a new window on the
  folder with the cursor at a file and line.

.DESCRIPTION
  Reads the screen's "vscode" object from <episode>\record.json:
    "vscode": {
      "folder": "C:\\lab\\pl01",                     // the neutral copy made by the episode prepare
      "goto": "demo/unsafe.ts:31:26",                // file:line[:column], relative to folder
      "settings": { "typescript.tsdk": "..." },      // optional, added to (and overriding) the recording settings
      "tasks": [ { "label": "...", "command": "..." } ],   // optional: shell tasks, run in pwsh -NoProfile
      "zoom": 1                                      // optional window.zoomLevel (default 1)
    }
  The window title becomes "<file> - <folder name> - VS Code"; window.json "title" for Record-Window.ps1 is
  "- <folder name> - VS Code" (printed at the end). Run from the episode folder (screen prepare statements do):
      & ..\..\..\tools\rec\Open-VsCodeScene.ps1 -Screen editor-never
  -Check validates the object against the episode folder itself (the folder is a copy of it) and prints the files it
  would write, without writing or opening anything (works on Linux too).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Screen,
    [string] $Episode = (Get-Location).Path,
    [switch] $Check
)
$ErrorActionPreference = 'Stop'

$def = Get-Content -LiteralPath (Join-Path $Episode 'record.json') -Raw | ConvertFrom-Json
$s = $def.screens | Where-Object name -eq $Screen
if (-not $s) { throw "Screen '$Screen' is not in $Episode\record.json" }
$vs = $s.vscode
if (-not $vs -or -not $vs.folder -or -not $vs.goto) { throw "Screen '$Screen' needs vscode.folder and vscode.goto" }
if ($vs.goto -notmatch '^(?<file>.+?):(?<line>\d+)(:(?<col>\d+))?$') { throw "vscode.goto must be file:line[:column], got '$($vs.goto)'" }
$file = $Matches.file; $line = [int]$Matches.line; $col = if ($Matches.col) { [int]$Matches.col } else { 1 }
$leaf = Split-Path $vs.folder -Leaf
$folder = if ($Check) { $Episode } else { $vs.folder }
if (-not (Test-Path -LiteralPath $folder)) { throw "Folder $folder does not exist (run the episode prepare first)" }
$target = Join-Path $folder $file
if (-not (Test-Path -LiteralPath $target)) { throw "goto file $file is not in $folder" }
$lines = @(Get-Content -LiteralPath $target)
if ($line -lt 1 -or $line -gt $lines.Count) { throw "goto line $line is outside $file ($($lines.Count) lines)" }
if ($col -gt $lines[$line - 1].Length + 1) { throw "goto column $col is past the end of line ${line}: '$($lines[$line - 1])'" }

# recording settings: readable at 1920x1032, nothing personal on screen, nothing that pops up during the take
$settings = [ordered]@{
    'workbench.colorTheme'                 = 'Default Dark Modern'
    'window.zoomLevel'                     = $(if ($null -ne $vs.zoom) { $vs.zoom } else { 1 })
    'editor.fontSize'                      = 18
    'terminal.integrated.fontSize'         = 16
    'window.title'                         = '${activeEditorShort} - ${rootName} - VS Code'
    'window.menuBarVisibility'             = 'classic'
    'workbench.activity.showAccounts'      = $false
    'workbench.startupEditor'              = 'none'
    'workbench.tips.enabled'               = $false
    'workbench.layoutControl.enabled'      = $false
    'chat.commandCenter.enabled'           = $false
    'chat.disableAIFeatures'               = $true
    'editor.minimap.enabled'               = $false
    'editor.stickyScroll.enabled'          = $false
    'editor.inlayHints.enabled'            = 'off'
    'editor.hover.delay'                   = 300
    'editor.hover.sticky'                  = $true
    'editor.occurrencesHighlight'          = 'off'
    'editor.lightbulb.enabled'             = 'off'
    'explorer.openEditors.visible'         = 0
    'files.exclude'                        = [ordered]@{ '.vscode' = $true; 'node_modules' = $true; '**/bin' = $true; '**/obj' = $true; '.venv' = $true }
    'task.autoDetect'                      = 'off'
    'npm.autoDetect'                       = 'off'
    'task.quickOpen.history'               = 0
    'terminal.integrated.tabs.enabled'     = $true
    'git.enabled'                          = $false
    'update.showReleaseNotes'              = $false
}
if ($vs.settings) { foreach ($p in $vs.settings.PSObject.Properties) { $settings[$p.Name] = $p.Value } }
$settingsJson = $settings | ConvertTo-Json -Depth 6

$tasksJson = $null
if ($vs.tasks) {
    $pwshShell = [ordered]@{ executable = 'pwsh.exe'; args = @('-NoProfile', '-NoLogo', '-Command') }
    $tasks = foreach ($t in @($vs.tasks)) {
        if (-not $t.label -or -not $t.command) { throw 'every vscode.tasks entry needs label and command' }
        [ordered]@{
            label = $t.label; type = 'shell'; command = $t.command; options = [ordered]@{ cwd = '${workspaceFolder}'; shell = $pwshShell }
            problemMatcher = @(); presentation = [ordered]@{ reveal = 'always'; panel = 'shared'; clear = $false; showReuseMessage = $false; echo = $true; focus = $false }
        }
    }
    $tasksJson = [ordered]@{ version = '2.0.0'; tasks = @($tasks) } | ConvertTo-Json -Depth 8
}

$title = "- $leaf - VS Code"
if ($Check) {
    Write-Host "vscode scene for $Screen OK: $($vs.folder) -> $file line $line col $col" -ForegroundColor Green
    Write-Host "  line ${line}: $($lines[$line - 1].Trim())"
    Write-Host "  window.json title: '$title'"
    Write-Host "  .vscode\settings.json:`n$settingsJson" -ForegroundColor DarkGray
    if ($tasksJson) { Write-Host "  .vscode\tasks.json:`n$tasksJson" -ForegroundColor DarkGray }
    return
}

if (-not $IsWindows) { throw 'Open-VsCodeScene opens VS Code on the recording laptop: Windows only (use -Check elsewhere)' }
$code = Get-Command code -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $code) { throw "'code' is not on the PATH (VS Code: 'Add to PATH' at install)" }
$dot = Join-Path $vs.folder '.vscode'
New-Item -ItemType Directory -Force -Path $dot | Out-Null
Set-Content -LiteralPath (Join-Path $dot 'settings.json') -Value $settingsJson -Encoding utf8
if ($tasksJson) { Set-Content -LiteralPath (Join-Path $dot 'tasks.json') -Value $tasksJson -Encoding utf8 }

& $code.Source -n $vs.folder -g "$($target):$($line):$($col)"
. (Join-Path $PSScriptRoot 'RecCommon.ps1')
try { $win = Wait-WindowByTitle -Title $title -TimeoutSeconds 60 }
catch { throw "VS Code did not show a window titled '*$title*' within 60 s (a Workspace Trust dialog may be waiting: click 'Yes, I trust the authors', then run this screen's prepare again)" }
Write-Host "VS Code ready: '$($win.Title)'. window.json title: '$title'" -ForegroundColor Green
