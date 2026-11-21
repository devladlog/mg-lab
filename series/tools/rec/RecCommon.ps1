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

if (-not ('MgRec.Win2' -as [type])) {
    Add-Type -Namespace MgRec -Name Win2 -MemberDefinition @'
public delegate bool EnumProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
public static System.Collections.Generic.List<IntPtr> found = new System.Collections.Generic.List<IntPtr>();
public static IntPtr FindContaining(string part) {
    IntPtr hit = IntPtr.Zero;
    EnumWindows(delegate (IntPtr h, IntPtr l) {
        if (!IsWindowVisible(h)) return true;
        var sb = new System.Text.StringBuilder(512);
        GetWindowText(h, sb, 512);
        if (sb.ToString().Contains(part)) { hit = h; return false; }
        return true;
    }, IntPtr.Zero);
    return hit;
}
public static string Title(IntPtr h) { var sb = new System.Text.StringBuilder(512); GetWindowText(h, sb, 512); return sb.ToString(); }
'@
}

function Wait-WindowByTitle([string]$Title, [int]$TimeoutSeconds = 20) {
    # matches part of the title: an elevated console is titled "Administrator: <title>"
    $end = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $h = [MgRec.Win2]::FindContaining($Title)
        if ($h -ne [IntPtr]::Zero) { return [pscustomobject]@{ Handle = $h; Title = [MgRec.Win2]::Title($h) } }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $end)
    throw "No window with '$Title' in its title appeared"
}

function Set-RecordingWindow([IntPtr]$Handle, [int]$Width = 1600, [int]$Height = 900) {
    # top-most, fixed size, on the primary screen, so nothing covers it while it is captured
    [void][MgRec.Win2]::ShowWindow($Handle, 1)
    [void][MgRec.Win2]::SetWindowPos($Handle, [IntPtr]::new(-1), 40, 40, $Width, $Height, 0x0040)
    [void][MgRec.Win2]::SetForegroundWindow($Handle)
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
