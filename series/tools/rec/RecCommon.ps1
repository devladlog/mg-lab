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

if (-not ('MgRec.Win3' -as [type])) {
    Add-Type -Namespace MgRec -Name Win3 -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
[DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr ctx);
[DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
public static int[] Bounds(IntPtr h) {
    RECT r; DwmGetWindowAttribute(h, 9, out r, System.Runtime.InteropServices.Marshal.SizeOf(typeof(RECT)));  // DWMWA_EXTENDED_FRAME_BOUNDS
    return new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
}
'@
}

function Get-WindowBounds([IntPtr]$Handle) {
    # visible frame in physical pixels (per-monitor DPI aware on this thread), for a screen-region capture
    [void][MgRec.Win3]::SetThreadDpiAwarenessContext([IntPtr]::new(-4))
    return [MgRec.Win3]::Bounds($Handle)
}

function Start-RegionCapture([string]$Ffmpeg, [int[]]$Bounds, [string]$OutFile, [switch]$DrawMouse) {
    # Screen-region capture: works for GPU-composed apps (Power BI, browsers, WebView2) that a window capture shows blank
    $x, $y, $w, $h = $Bounds; $w -= $w % 2; $h -= $h % 2
    $psi = [Diagnostics.ProcessStartInfo]::new($Ffmpeg)
    $mouse = if ($DrawMouse) { '1' } else { '0' }
    foreach ($a in @('-loglevel', 'error', '-y', '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', $mouse,
            '-offset_x', "$x", '-offset_y', "$y", '-video_size', "${w}x${h}", '-i', 'desktop',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', $OutFile)) { $psi.ArgumentList.Add($a) }
    $psi.RedirectStandardInput = $true; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    return [Diagnostics.Process]::Start($psi)
}

function Set-RecordingWindow([IntPtr]$Handle, [int]$Width = 1600, [int]$Height = 900, [int]$X = 40, [int]$Y = 40) {
    # top-most, fixed size, on the primary screen, so nothing covers it while it is captured
    [void][MgRec.Win2]::ShowWindow($Handle, 1)
    [void][MgRec.Win2]::SetWindowPos($Handle, [IntPtr]::new(-1), $X, $Y, $Width, $Height, 0x0040)
    [void][MgRec.Win2]::SetForegroundWindow($Handle)
}

function Start-WindowCapture([string]$Ffmpeg, [string]$Title, [string]$OutFile, [switch]$DrawMouse) {
    $psi = [Diagnostics.ProcessStartInfo]::new($Ffmpeg)
    $mouse = if ($DrawMouse) { '1' } else { '0' }   # app and browser scenes show the pointer; terminals don't need it
    foreach ($a in @('-loglevel', 'error', '-y', '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', $mouse, '-i', "title=$Title",
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
