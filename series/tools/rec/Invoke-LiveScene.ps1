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
$Host.UI.RawUI.WindowTitle = $(if ($scene.windowTitle) { $scene.windowTitle } else { 'MG-REC' })
# large, readable font inside this console (the window is recorded at 1600x900)
try {
    Add-Type -Namespace MgRec -Name Font -MemberDefinition @'
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct CONSOLE_FONT_INFOEX { public uint cbSize; public uint nFont; public short X; public short Y; public int FontFamily; public int FontWeight;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string FaceName; }
[DllImport("kernel32.dll", SetLastError = true)] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] public static extern bool SetCurrentConsoleFontEx(IntPtr h, bool max, ref CONSOLE_FONT_INFOEX f);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@
    $f = New-Object MgRec.Font+CONSOLE_FONT_INFOEX
    $f.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($f); $f.FaceName = 'Cascadia Mono'; $f.Y = $(if ($scene.fontSize) { [int16]$scene.fontSize } else { 22 }); $f.FontWeight = 400; $f.FontFamily = 54
    [void][MgRec.Font]::SetCurrentConsoleFontEx([MgRec.Font]::GetStdHandle(-11), $false, [ref]$f)
    # colours from npm, vitest, dotnet etc. arrive as ANSI escapes: let the console render them instead of printing them
    $h = [MgRec.Font]::GetStdHandle(-11); $m = 0
    if ([MgRec.Font]::GetConsoleMode($h, [ref]$m)) { [void][MgRec.Font]::SetConsoleMode($h, $m -bor 0x0001 -bor 0x0004) }
} catch {}
# UTF-8 both ways, so tool symbols (check marks, crosses, box drawing) don't turn into mojibake
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); [Console]::InputEncoding = [Text.UTF8Encoding]::new($false); $OutputEncoding = [Text.UTF8Encoding]::new($false) } catch {}
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
if ($target -eq 'host') {
    # child PowerShell processes started on camera skip the owner's profile (no personal banner or prompt in the video);
    # the typed command stays exactly as written in record.json
    $global:MgPwshExe = (Get-Command pwsh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ($global:MgPwshExe) { function global:pwsh { & $global:MgPwshExe -NoProfile @args } }
    $global:MgPsExe = (Get-Command powershell -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ($global:MgPsExe) { function global:powershell { & $global:MgPsExe -NoProfile @args } }
    # third-party pytest plugins installed per user (e.g. anyio) print warnings with their site-packages path, which
    # holds the Windows user name: keep them out of on-camera test runs (pytest's own plugins are unaffected)
    $env:PYTEST_ADDOPTS = (("$env:PYTEST_ADDOPTS -p no:anyio -p no:cacheprovider").Trim())
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
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
