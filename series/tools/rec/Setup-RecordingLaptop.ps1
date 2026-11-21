#Requires -RunAsAdministrator
<#
.SYNOPSIS
  One-time setup of the recording laptop for live-session recordings. Run once in an elevated PowerShell, from the repo
  folder:  powershell -ExecutionPolicy Bypass -File .\series\tools\rec\Setup-RecordingLaptop.ps1
  What it does (and nothing else):
   1. adds you to the local "Hyper-V Administrators" group, so the lab VMs can be started and reached with
      PowerShell Direct without an elevated window (takes effect after you sign out and in once);
   2. installs ffmpeg with winget (Gyan.FFmpeg) if it is missing - you accept winget's source/package agreements;
   3. sets a large, readable font for the console window the recorder opens (HKCU\Console, pwsh only);
   4. writes .vscode\tasks.json with the lab, verification and recording tasks.
#>
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
# the elevated window may run as the same user; that's the one we add
Write-Host "1/4 Hyper-V Administrators: $me" -ForegroundColor Cyan
$group = (Get-LocalGroup -SID 'S-1-5-32-578').Name
if (-not (Get-LocalGroupMember -Group $group | Where-Object Name -eq $me)) { Add-LocalGroupMember -Group $group -Member $me; $signOut = $true }
else { Write-Host '   already a member' }

Write-Host '2/4 ffmpeg' -ForegroundColor Cyan
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --scope user --accept-source-agreements --accept-package-agreements
} else { Write-Host '   already installed' }

Write-Host '3/4 console font for recordings' -ForegroundColor Cyan
$pwsh = (Get-Command pwsh).Source
$key = 'HKCU:\Console\' + ($pwsh -replace '\\', '_')
New-Item -Path $key -Force | Out-Null
Set-ItemProperty $key FaceName 'Cascadia Mono'
Set-ItemProperty $key FontSize 0x00180000 -Type DWord      # 24 px
Set-ItemProperty $key FontWeight 400 -Type DWord
Set-ItemProperty $key WindowSize 0x00230082 -Type DWord    # 130 x 35
Set-ItemProperty $key ScreenBufferSize 0x0bb80082 -Type DWord
Set-ItemProperty $key QuickEdit 0 -Type DWord

Write-Host '4/4 VS Code tasks' -ForegroundColor Cyan
function T($label, $cmd) {
    @{ label = $label; type = 'process'; command = 'pwsh.exe'; problemMatcher = @(); presentation = @{ reveal = 'always'; panel = 'dedicated' }
       args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd) }
}
$tasks = @{ version = '2.0.0'; tasks = @(
    @{ label = 'MG 1: toolchain report'; type = 'process'; command = 'powershell.exe'; problemMatcher = @()
       args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '${workspaceFolder}\series\tools\Get-WindowsToolchain.ps1') }
    (T 'MG 2: verify all episodes on Windows (.NET + Pester)' "New-Item -ItemType Directory -Force '`${workspaceFolder}\verify-results' | Out-Null; Start-Transcript '`${workspaceFolder}\verify-results\transcript.txt' -Force | Out-Null; try { & '`${workspaceFolder}\series\tools\Invoke-WindowsVerification.ps1' } finally { Stop-Transcript | Out-Null }")
    (T 'MG R1: lab - start VMs' "& '`${workspaceFolder}\series\tools\rec\Start-LabVMs.ps1'")
    (T 'MG R2: record the queue (recordings\queue.txt)' "New-Item -ItemType Directory -Force '`${workspaceFolder}\recordings' | Out-Null; Start-Transcript '`${workspaceFolder}\recordings\transcript.txt' -Force | Out-Null; try { & '`${workspaceFolder}\series\tools\rec\Invoke-RecordingQueue.ps1' } finally { Stop-Transcript | Out-Null }")
    (T 'MG R3: lab - stop VMs' "& '`${workspaceFolder}\series\tools\rec\Start-LabVMs.ps1' -Stop")
) }
New-Item -ItemType Directory -Force -Path (Join-Path $root '.vscode'), (Join-Path $root 'recordings') | Out-Null
$tasks | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $root '.vscode\tasks.json') -Encoding utf8

Write-Host "`nDone." -ForegroundColor Green
if ($signOut) { Write-Host 'Sign out of Windows and back in once, so the Hyper-V Administrators membership applies.' -ForegroundColor Yellow }
