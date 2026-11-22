# Shared helpers for the recording kit (dot-sourced).

function Get-FfmpegPath {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $winget = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winget) { return $winget.FullName }
    throw 'ffmpeg not found: run series\tools\rec\Setup-RecordingLaptop.ps1 once (it installs it with winget).'
}

$script:LabCredentialPath = 'E:\MGLab\secrets\lab-admin.xml'

function Get-LabCredential {
    $path = $script:LabCredentialPath
    if (-not (Test-Path -LiteralPath $path)) { throw "Lab credential file not found: $path" }
    $c = Import-Clixml -LiteralPath $path
    if ($c.UserName -notmatch '\\|@') { return [pscredential]::new("CONTOSO\$($c.UserName)", $c.Password) }
    $c
}

function Invoke-HostStatements {
    # Runs preparation statements on the laptop (not recorded). $cred (lab credential) and $EpisodeRoot are available.
    # The lab credential file is only needed by statements that use $cred or reach a VM (-VMName, PowerShell Direct):
    # when the file is missing, host-only statements still run and such a statement fails before it runs.
    param([string[]] $Statements, [string] $EpisodeRoot)
    $cred = if (Test-Path -LiteralPath $script:LabCredentialPath) { Get-LabCredential } else { $null }
    Push-Location $EpisodeRoot
    try {
        foreach ($st in $Statements) {
            Write-Host "  > $st" -ForegroundColor DarkGray
            if (-not $cred -and -not $st.TrimStart().StartsWith('#') -and $st -match '\$cred\b|-VMName\b') {
                throw "This statement needs the lab credential (`$cred / PowerShell Direct), but $($script:LabCredentialPath) is missing: $st"
            }
            Invoke-Expression $st | Out-Host
        }
    } finally { Pop-Location }
}

function Get-PythonExe {
    # For prepare_local statements: full path of a python.exe of the given version (e.g. '3.13'), installed per user
    # with winget (no admin rights) when it is missing. The laptop's default `python` (3.10) is left alone.
    param([Parameter(Mandatory)] [string] $Version)
    $nodot = $Version.Replace('.', '')
    $find = {
        $c = @()
        if (Get-Command py -ErrorAction SilentlyContinue) { $c += @(py "-$Version" -c 'import sys; print(sys.executable)' 2>$null) }
        $c += "$env:LOCALAPPDATA\Programs\Python\Python$nodot\python.exe", "$env:ProgramFiles\Python$nodot\python.exe"
        $c | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    }
    $exe = & $find
    if (-not $exe) {
        winget install --id "Python.Python.$Version" -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $exe = & $find
    }
    if (-not $exe) { throw "Python $Version is missing and winget did not install it (winget install --id Python.Python.$Version --scope user)" }
    $exe
}

function Use-DotNetSdk {
    # For prepare_local statements: makes a .NET SDK of the given channel (and, optionally, extra runtimes such as '8.0')
    # available to this process and to the scene windows it starts. The dotnet on PATH is used when it has them;
    # otherwise they are installed without admin rights into C:\MGLab\dotnet (outside the user profile, so no profile
    # path can reach the camera) and that folder goes first on PATH for this process only.
    param([string] $Channel = '10.0', [string[]] $Runtime = @())
    $major = $Channel.Split('.')[0]
    $has = {
        $d = Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $d) { return $false }
        $sdks = @(& $d.Source --list-sdks 2>$null); $rts = @(& $d.Source --list-runtimes 2>$null)
        if (-not ($sdks -match "^$major\.")) { return $false }
        foreach ($r in $Runtime) { if (-not ($rts -match "^Microsoft\.NETCore\.App $([regex]::Escape($r))\.")) { return $false } }
        $true
    }
    if (& $has) { return }
    $dir = 'C:\MGLab\dotnet'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $installer = Join-Path $dir 'dotnet-install.ps1'
    if (-not (Test-Path $installer)) { Invoke-WebRequest -Uri 'https://dot.net/v1/dotnet-install.ps1' -OutFile $installer -UseBasicParsing }
    Write-Host "  installing .NET SDK $Channel into $dir" -ForegroundColor DarkGray
    & $installer -Channel $Channel -InstallDir $dir -NoPath | Out-Host
    foreach ($r in $Runtime) { & $installer -Runtime dotnet -Channel $r -InstallDir $dir -NoPath | Out-Host }
    $env:DOTNET_ROOT = $dir; $env:DOTNET_MULTILEVEL_LOOKUP = '0'
    if ($env:PATH -notlike "$dir;*") { $env:PATH = "$dir;$env:PATH" }
    if (-not (& $has)) { throw ".NET SDK $Channel is still not available after installing it into $dir" }
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

if (-not ('MgRec.Win4' -as [type])) {
    Add-Type -Namespace MgRec -Name Win4 -MemberDefinition @'
public delegate bool EnumProc4(IntPtr h, IntPtr l);
[DllImport("user32.dll")] static extern bool EnumWindows(EnumProc4 cb, IntPtr l);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[StructLayout(LayoutKind.Sequential)] public struct POINT4 { public int X, Y; }
[StructLayout(LayoutKind.Sequential)] public struct RECT4 { public int Left, Top, Right, Bottom; }
[StructLayout(LayoutKind.Sequential)] public struct WINDOWPLACEMENT { public int length; public int flags; public int showCmd; public POINT4 ptMinPosition; public POINT4 ptMaxPosition; public RECT4 rcNormalPosition; }
[DllImport("user32.dll")] static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);
[DllImport("user32.dll")] static extern bool SetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);
[DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
// first top-level window whose title contains the text, hidden ones included
public static IntPtr FindAny(string part) {
    IntPtr hit = IntPtr.Zero;
    EnumWindows(delegate (IntPtr h, IntPtr l) {
        var sb = new System.Text.StringBuilder(512);
        GetWindowText(h, sb, 512);
        if (sb.ToString().Contains(part)) { hit = h; return false; }
        return true;
    }, IntPtr.Zero);
    return hit;
}
// shows a (hidden) window at the given place without activating it, behind every other window
public static void ShowBehind(IntPtr h, int x, int y, int w, int hgt) {
    WINDOWPLACEMENT p = new WINDOWPLACEMENT();
    p.length = System.Runtime.InteropServices.Marshal.SizeOf(typeof(WINDOWPLACEMENT));
    GetWindowPlacement(h, ref p);
    p.showCmd = 4;   // SW_SHOWNOACTIVATE
    p.rcNormalPosition.Left = x; p.rcNormalPosition.Top = y; p.rcNormalPosition.Right = x + w; p.rcNormalPosition.Bottom = y + hgt;
    SetWindowPlacement(h, ref p);
    SetWindowPos(h, new IntPtr(1), x, y, w, hgt, 0x0010);   // HWND_BOTTOM, SWP_NOACTIVATE
}
'@
}

function Wait-HiddenWindowByTitle([string]$Title, [int]$TimeoutSeconds = 20) {
    # like Wait-WindowByTitle, for a window that was started hidden (background takes)
    $end = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $h = [MgRec.Win4]::FindAny($Title)
        if ($h -ne [IntPtr]::Zero) { return [pscustomobject]@{ Handle = $h; Title = [MgRec.Win2]::Title($h) } }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $end)
    throw "No window with '$Title' in its title appeared"
}

function Set-RecordingWindow([IntPtr]$Handle, [int]$Width = 1600, [int]$Height = 900, [int]$X = 40, [int]$Y = 40, [switch]$NotTopMost, [switch]$Background) {
    # fixed size and position; top-most (terminals) so nothing covers it, or just in front (apps: a top-most window
    # would hide the app's own dialogs, which open behind it). -Background (terminals): never activated and behind
    # every other window: a window capture reads the window itself, so it need not be seen, and whoever is using
    # the laptop (or a browser take on the same screen) is not disturbed.
    if ($Background) { [MgRec.Win4]::ShowBehind($Handle, $X, $Y, $Width, $Height); return }
    [void][MgRec.Win2]::ShowWindow($Handle, 1)
    $after = if ($NotTopMost) { [IntPtr]::Zero } else { [IntPtr]::new(-1) }
    [void][MgRec.Win2]::SetWindowPos($Handle, $after, $X, $Y, $Width, $Height, 0x0040)
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
    # several recorder lanes write this file: a write that meets another one is tried again, and never fails a take
    $log = Join-Path $Root 'recordings-log.jsonl'
    $line = ($Entry | ConvertTo-Json -Compress)
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -LiteralPath $log -Value $line -Encoding utf8 -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 200 }
    }
    Write-Host "recordings-log.jsonl was busy; not logged: $line" -ForegroundColor Yellow
}

function Get-ForbiddenText {
    # Text of the signed-in cloud account that must never be on camera: the account e-mail (and its part before the @),
    # the display name, and the subscription, tenant and object ids. Read once per recorder process from the Azure CLI
    # session and kept in memory only (MGREC_FORBIDDEN); nothing when the Azure CLI is missing or signed out.
    if (-not $env:MGREC_FORBIDDEN) {
        $ErrorActionPreference = 'Continue'   # here only: a warning on the Azure CLI's stderr must not empty the list
        $vals = @()
        try {
            if (Get-Command az -ErrorAction SilentlyContinue) {
                $a = @(az account show --query '[id, tenantId, user.name]' -o tsv 2>$null)
                if ($LASTEXITCODE -eq 0) { $vals += $a | ForEach-Object { "$_" -split "`t" } }
                $u = @(az ad signed-in-user show --query '[displayName, userPrincipalName, id]' -o tsv 2>$null)
                if ($LASTEXITCODE -eq 0) { $vals += $u | ForEach-Object { "$_" -split "`t" } }
            }
        } catch {}
        $vals += @($vals | Where-Object { "$_" -match '^([^@\s]+)@' } | ForEach-Object { ("$_" -split '@')[0] })
        $keep = @($vals | ForEach-Object { "$_".Trim() } | Where-Object { $_.Length -ge 6 } | Select-Object -Unique)
        $env:MGREC_FORBIDDEN = if ($keep) { $keep -join '|' } else { '-' }
    }
    @($env:MGREC_FORBIDDEN -split '\|' | Where-Object { $_.Length -ge 6 })
}
