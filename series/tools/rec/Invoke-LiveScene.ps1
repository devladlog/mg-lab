#Requires -Version 7.2
<#
.SYNOPSIS
  Plays one recording scene live: types each command on screen and runs it for real, on this laptop or inside a lab VM
  (PowerShell Direct). Nothing is faked: the output on screen is the real output. Started by Record-Scene.ps1 inside
  the window that is being recorded.
.PARAMETER SceneFile
  JSON written by Record-Scene.ps1: { title, target, workdir, prompt, commands[], typingDelayMs, markerDir }
#>
param([Parameter(Mandatory)] [string] $SceneFile)

$ErrorActionPreference = 'Continue'
$scene = Get-Content -LiteralPath $SceneFile -Raw | ConvertFrom-Json
$Host.UI.RawUI.WindowTitle = 'MG-REC'
if ($scene.markerDir) {
    New-Item -ItemType File -Force -Path (Join-Path $scene.markerDir 'started') | Out-Null
    try { Start-Transcript -Path (Join-Path $scene.markerDir 'scene.log') -Force | Out-Null } catch {}
}
try { $Host.UI.RawUI.BackgroundColor = 'Black'; $Host.UI.RawUI.ForegroundColor = 'Gray' } catch {}
Clear-Host

$delay = if ($scene.typingDelayMs) { [int]$scene.typingDelayMs } else { 28 }
$prompt = if ($scene.prompt) { $scene.prompt } else { 'PS> ' }
$session = $null
$target = if ($scene.target) { "$($scene.target)" } else { 'host' }

function Get-LabCredential {
    $path = 'E:\MGLab\secrets\lab-admin.xml'
    if (-not (Test-Path $path)) { throw "Lab credential file not found: $path" }
    $c = Import-Clixml -LiteralPath $path
    if ($c -is [pscredential]) {
        if ($c.UserName -notmatch '\\|@') { return [pscredential]::new("CONTOSO\$($c.UserName)", $c.Password) }
        return $c
    }
    throw 'lab-admin.xml does not hold a credential'
}

function Write-Typed([string]$text) {
    foreach ($ch in $text.ToCharArray()) {
        Write-Host -NoNewline $ch
        if ($ch -ne ' ') { Start-Sleep -Milliseconds (Get-Random -Minimum ([int]($delay * 0.5)) -Maximum ([int]($delay * 1.6))) }
    }
    Write-Host ''
}

if ($target -ne 'host') {
    try {
        $sp = @{ VMName = $target; Credential = (Get-LabCredential); ErrorAction = 'Stop' }
        if ($scene.configurationName) { $sp.ConfigurationName = "$($scene.configurationName)" }
        $session = New-PSSession @sp
        if ($scene.workdir) { Invoke-Command -Session $session -ScriptBlock { Set-Location $using:scene.workdir } }
    } catch {
        Write-Host "Could not open PowerShell Direct to ${target}: $($_.Exception.Message)" -ForegroundColor Red
        exit 2
    }
} elseif ($scene.workdir) {
    Set-Location -LiteralPath $scene.workdir
}

Start-Sleep -Milliseconds 800
foreach ($cmd in $scene.commands) {
    $line = "$cmd"
    if ($line -match '^#pause\s+(\d+(\.\d+)?)') { Start-Sleep -Seconds ([double]$Matches[1]); continue }
    if ($line -match '^#clear') { Clear-Host; continue }
    Write-Host -NoNewline $prompt -ForegroundColor Green
    Write-Typed $line
    if ($line.TrimStart().StartsWith('#')) { Start-Sleep -Milliseconds 500; continue }
    Start-Sleep -Milliseconds 250
    try {
        if ($session) {
            $out = Invoke-Command -Session $session -ScriptBlock {
                $ErrorActionPreference = 'Continue'
                try { Invoke-Expression $using:line 2>&1 | Out-String -Width 150 } catch { $_ | Out-String -Width 150 }
            }
            if ($out) { Write-Host ($out.TrimEnd()) }
        } else {
            Invoke-Expression $line 2>&1 | Out-Host
        }
    } catch {
        Write-Host ($_ | Out-String) -ForegroundColor Red
    }
    Start-Sleep -Milliseconds 900
}
Write-Host -NoNewline $prompt -ForegroundColor Green
Start-Sleep -Seconds 2

# Tell the recorder the scene is finished, then wait until it has stopped recording before the window closes.
if ($scene.markerDir) {
    New-Item -ItemType File -Force -Path (Join-Path $scene.markerDir 'done') | Out-Null
    $stop = Join-Path $scene.markerDir 'stop'
    for ($i = 0; $i -lt 300 -and -not (Test-Path $stop); $i++) { Start-Sleep -Milliseconds 200 }
}
if ($session) { Remove-PSSession $session }
