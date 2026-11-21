# Shared helpers for the recording kit (dot-sourced).

function Get-FfmpegPath {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $winget = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winget) { return $winget.FullName }
    throw 'ffmpeg not found: run series\tools\rec\Setup-RecordingLaptop.ps1 once (it installs it with winget).'
}

function Get-LabCredential {
    $path = 'E:\MGLab\secrets\lab-admin.xml'
    $c = Import-Clixml -LiteralPath $path
    if ($c.UserName -notmatch '\\|@') { return [pscredential]::new("CONTOSO\$($c.UserName)", $c.Password) }
    $c
}

function Invoke-HostStatements {
    # Runs preparation statements on the laptop (not recorded). $cred (lab credential) and $EpisodeRoot are available.
    param([string[]] $Statements, [string] $EpisodeRoot)
    $cred = Get-LabCredential
    Push-Location $EpisodeRoot
    try {
        foreach ($st in $Statements) {
            Write-Host "  > $st" -ForegroundColor DarkGray
            Invoke-Expression $st | Out-Host
        }
    } finally { Pop-Location }
}

if (-not ('MgRec.Win' -as [type])) {
    Add-Type -Namespace MgRec -Name Win -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
'@
}

function Wait-WindowByTitle([string]$Title, [int]$TimeoutSeconds = 20) {
    $end = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $h = [MgRec.Win]::FindWindow($null, $Title)
        if ($h -ne [IntPtr]::Zero) { return $h }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $end)
    throw "Window '$Title' did not appear"
}

function Set-RecordingWindow([IntPtr]$Handle, [int]$Width = 1600, [int]$Height = 900) {
    # top-most, fixed size, on the primary screen, so nothing covers it while it is captured
    [void][MgRec.Win]::ShowWindow($Handle, 1)
    [void][MgRec.Win]::SetWindowPos($Handle, [IntPtr]::new(-1), 40, 40, $Width, $Height, 0x0040)
    [void][MgRec.Win]::SetForegroundWindow($Handle)
}

function Start-WindowCapture([string]$Ffmpeg, [string]$Title, [string]$OutFile) {
    $psi = [Diagnostics.ProcessStartInfo]::new($Ffmpeg)
    foreach ($a in @('-loglevel', 'error', '-y', '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', '0', '-i', "title=$Title",
            '-vf', 'crop=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', $OutFile)) { $psi.ArgumentList.Add($a) }
    $psi.RedirectStandardInput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    [Diagnostics.Process]::Start($psi)
}

function Stop-WindowCapture([Diagnostics.Process]$Process) {
    try { $Process.StandardInput.Write('q'); $Process.StandardInput.Flush() } catch {}
    if (-not $Process.WaitForExit(15000)) { $Process.Kill() }
}

function Add-RecordingLog([string]$Root, $Entry) {
    $log = Join-Path $Root 'recordings-log.jsonl'
    ($Entry | ConvertTo-Json -Compress) | Add-Content -LiteralPath $log -Encoding utf8
}
