#Requires -Version 7.2
<#
.SYNOPSIS
  Runs a command and delivers a real Ctrl+C to it after a fixed delay, so the program's own Ctrl+C handler runs
  (Console.CancelKeyPress in .NET, process.on('SIGINT') in Node) without anyone pressing a key.

.DESCRIPTION
  Dot-source it to get the function (Invoke-LiveScene.ps1 does this for every host scene):
      Send-CtrlC -AfterMs 1500 { dotnet run --no-build --project src\Contoso.Approvals.Cli -- sequential }
  The scriptblock runs in the current console. After -AfterMs milliseconds a CTRL_C_EVENT is generated on that
  console with GenerateConsoleCtrlEvent, the same signal the console sends when Ctrl+C is pressed. The calling
  PowerShell ignores that one event (SetConsoleCtrlHandler(NULL, TRUE), set only after the command has started, so
  the command itself does not inherit the "ignore" flag) and restores normal Ctrl+C handling when the command has
  ended. $LASTEXITCODE is the command's own exit code; its stderr is shown as plain lines with its stdout. If the command ends before the delay, nothing is sent and a
  warning says so. On Linux/macOS (build container) SIGINT is sent to the processes started by the command.

  Run it as a script for the checks used by the screen prepares (both open their own hidden console on Windows, so
  the console of the caller - the window recorder - never sees a Ctrl+C):
      Send-CtrlC.ps1 -SelfTest
          a child process with a Ctrl+C handler must report the signal and exit 130, and the caller must survive.
      Send-CtrlC.ps1 -Rehearse -WorkingDirectory C:\lab\pl09 -AfterMs 500 -Command 'node src/cli.js ...' `
                     -Expect 'stopped: interrupted' -ExpectExitCode 130 [-Reject 'ready,'] [-LogFile x.log]
          plays the real command off camera with the Ctrl+C, then checks its output and exit code (also a JIT/disk
          warm-up before the take). Throws when a check fails.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch] $SelfTest,
    [switch] $Rehearse,
    [string] $WorkingDirectory,
    [string] $Command,
    [int] $AfterMs = 1500,
    [string[]] $Expect = @(),
    [string[]] $Reject = @(),
    [Nullable[int]] $ExpectExitCode,
    [string] $LogFile,
    [int] $TimeoutSeconds = 90,
    # internal: the part of -SelfTest / -Rehearse that runs inside the hidden console
    [switch] $Inner,
    [switch] $SelfTestChild,
    [string] $ResultFile,
    [string] $CommandBase64
)

if (-not ('MgRec.CtrlC' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
namespace MgRec {
public static class CtrlC {
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);
    [DllImport("libc", SetLastError = true, EntryPoint = "kill")] static extern int SysKill(int pid, int sig);
    static ManualResetEventSlim cancel;
    static Thread worker;
    public static volatile bool Sent;
    public static volatile string Error;

    static bool IsWindows { get { return RuntimeInformation.IsOSPlatform(OSPlatform.Windows); } }

    // Schedules one Ctrl+C on this console after ms milliseconds (Windows), or SIGINT to the processes started by
    // this process (Linux/macOS). Cancel() before it fires sends nothing.
    public static void Schedule(int ms, int selfPid) {
        Sent = false; Error = null;
        cancel = new ManualResetEventSlim(false);
        var c = cancel;
        worker = new Thread(() => {
            if (c.Wait(ms)) return;
            try {
                if (IsWindows) {
                    // this process ignores the event; processes started before this call keep their own handlers
                    SetConsoleCtrlHandler(IntPtr.Zero, true);
                    if (GenerateConsoleCtrlEvent(0 /* CTRL_C_EVENT */, 0 /* every process on this console */)) Sent = true;
                    else Error = "GenerateConsoleCtrlEvent failed, Win32 error " + Marshal.GetLastWin32Error();
                } else {
                    var kids = Descendants(selfPid);
                    foreach (var pid in kids) SysKill(pid, 2 /* SIGINT */);
                    Sent = kids.Count > 0;
                    if (!Sent) Error = "no child process to signal";
                }
            } catch (Exception e) { Error = e.Message; }
        });
        worker.IsBackground = true;
        worker.Start();
    }

    // Stops a pending Ctrl+C, waits for the worker, then (Windows) restores normal Ctrl+C handling for this process.
    public static void Finish(int settleMs) {
        if (cancel != null) cancel.Set();
        if (worker != null) worker.Join(5000);
        if (IsWindows) { Thread.Sleep(settleMs); SetConsoleCtrlHandler(IntPtr.Zero, false); }
    }

    static List<int> Descendants(int root) {
        var parent = new Dictionary<int, int>();
        foreach (var dir in Directory.GetDirectories("/proc")) {
            int pid;
            if (!int.TryParse(Path.GetFileName(dir), out pid)) continue;
            try {
                var stat = File.ReadAllText(Path.Combine(dir, "stat"));
                var rest = stat.Substring(stat.LastIndexOf(')') + 2).Split(' ');
                parent[pid] = int.Parse(rest[1]);
            } catch { }
        }
        var result = new List<int>();
        var queue = new Queue<int>(); queue.Enqueue(root);
        while (queue.Count > 0) {
            var p = queue.Dequeue();
            foreach (var kv in parent) if (kv.Value == p && kv.Key != root) { result.Add(kv.Key); queue.Enqueue(kv.Key); }
        }
        return result;
    }
}
public static class CtrlCChild {
    // Self-test child: waits for one Ctrl+C, reports it and exits 130; exits 1 when none arrives in time.
    public static int Run(int waitMs) {
        var got = new ManualResetEventSlim(false);
        Console.CancelKeyPress += (s, e) => { e.Cancel = true; got.Set(); };
        Console.Out.WriteLine("child: waiting for Ctrl+C"); Console.Out.Flush();
        // Environment.Exit: the PowerShell host of this child would otherwise turn the stopped pipeline into exit 0
        if (got.Wait(waitMs)) { Console.Out.WriteLine("child: got Ctrl+C"); Console.Out.Flush(); Environment.Exit(130); }
        Console.Out.WriteLine("child: no Ctrl+C within " + waitMs + " ms"); Console.Out.Flush();
        return 1;
    }
}
}
'@
}

function Send-CtrlC {
    <#
    .SYNOPSIS
      Runs -Command and sends a real Ctrl+C to it after -AfterMs milliseconds (see Send-CtrlC.ps1).
    #>
    param(
        [Parameter(Mandatory, Position = 0)] [scriptblock] $Command,
        [int] $AfterMs = 1500
    )
    [MgRec.CtrlC]::Schedule($AfterMs, $PID)
    # stderr joins stdout as plain lines: programs print their Ctrl+C message on stderr, and Invoke-Expression ... 2>&1
    # in the scene player does not show a native command's stderr in every host
    try { & $Command 2>&1 | ForEach-Object { if ($_ -is [Management.Automation.ErrorRecord]) { "$_" } else { $_ } } }
    finally {
        [MgRec.CtrlC]::Finish(300)
        if ([MgRec.CtrlC]::Error) { Write-Warning "Ctrl+C not sent: $([MgRec.CtrlC]::Error)" }
        elseif (-not [MgRec.CtrlC]::Sent) { Write-Warning "The command ended before the Ctrl+C (after $AfterMs ms) was sent." }
    }
}

# --- script entry points (nothing below runs when the file is dot-sourced without switches) --------------------------
$self = $PSCommandPath
$pwshExe = @((Join-Path $PSHOME 'pwsh.exe'), (Join-Path $PSHOME 'pwsh')) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $pwshExe) { $pwshExe = (Get-Command pwsh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
$onWindows = $IsWindows

function Invoke-InHiddenConsole([string[]] $Arguments, [int] $Timeout) {
    # Windows: a new (hidden) console, so the Ctrl+C stays inside it. Elsewhere: a plain child process.
    $all = @('-NoProfile', '-NoLogo', '-File', $self) + $Arguments
    # Start-Process joins -ArgumentList with spaces and does not quote: quote here (the command text travels as base64)
    $quoted = $all | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }
    $p = if ($onWindows) { Start-Process -FilePath $pwshExe -ArgumentList $quoted -WindowStyle Hidden -PassThru }
         else { Start-Process -FilePath $pwshExe -ArgumentList $quoted -PassThru }
    if (-not $p.WaitForExit($Timeout * 1000)) { try { $p.Kill($true) } catch {}; throw "timed out after $Timeout s" }
}

if ($SelfTestChild) {
    exit ([MgRec.CtrlCChild]::Run(15000))
}

if ($Inner -and $SelfTest) {
    $out = Send-CtrlC -AfterMs $AfterMs { & $pwshExe -NoProfile -NoLogo -File $self -SelfTestChild } 2>&1 | Out-String
    $code = $LASTEXITCODE
    # reaching this line at all proves the caller survived the Ctrl+C
    Set-Content -LiteralPath $ResultFile -Value ("exit=$code sent=$([MgRec.CtrlC]::Sent)`n" + $out) -Encoding utf8
    exit 0
}

if ($Inner -and $Rehearse) {
    Set-Location -LiteralPath $WorkingDirectory
    $sb = [scriptblock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($CommandBase64)))
    $out = Send-CtrlC -AfterMs $AfterMs $sb *>&1 | Out-String -Width 200
    $code = $LASTEXITCODE
    Set-Content -LiteralPath $ResultFile -Value ("exit=$code sent=$([MgRec.CtrlC]::Sent)`n" + $out) -Encoding utf8
    exit 0
}

if ($SelfTest -or $Rehearse) {
    $result = Join-Path ([IO.Path]::GetTempPath()) ("mg-ctrlc-" + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    try {
        if ($SelfTest) {
            # the child needs about a second to compile its handler: send the Ctrl+C after 4 s, it waits up to 15 s
            Invoke-InHiddenConsole -Arguments @('-Inner', '-SelfTest', '-AfterMs', '4000', '-ResultFile', $result) -Timeout 60
        } else {
            if (-not $WorkingDirectory -or -not $Command) { throw '-Rehearse needs -WorkingDirectory and -Command' }
            Invoke-InHiddenConsole -Arguments @('-Inner', '-Rehearse', '-WorkingDirectory', $WorkingDirectory, '-CommandBase64', [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command)), '-AfterMs', "$AfterMs", '-ResultFile', $result) -Timeout $TimeoutSeconds
        }
        if (-not (Test-Path -LiteralPath $result)) { throw 'the caller did not survive the Ctrl+C (no result written)' }
        $text = Get-Content -LiteralPath $result -Raw
        if ($LogFile) { Set-Content -LiteralPath $LogFile -Value $text -Encoding utf8 }
        $null = $text -match '^exit=(-?\d*) sent=(\w+)'
        $code = if ($Matches[1] -ne '') { [int]$Matches[1] } else { $null }; $sent = $Matches[2] -eq 'True'
        $what = if ($SelfTest) { 'Send-CtrlC self-test' } else { "Rehearsal ($Command, Ctrl+C after $AfterMs ms)" }
        $fail = @()
        if (-not $sent) { $fail += 'no Ctrl+C was sent (the command ended first, or the call failed)' }
        if ($SelfTest) {
            if ($code -ne 130) { $fail += "child exit code $code, expected 130" }
            if ($text -notmatch 'child: got Ctrl\+C') { $fail += "child did not report the Ctrl+C" }
        } else {
            if ($null -ne $ExpectExitCode -and $code -ne $ExpectExitCode) { $fail += "exit code $code, expected $ExpectExitCode" }
            foreach ($e in $Expect) { if ($text -notmatch $e) { $fail += "output lacks /$e/" } }
            foreach ($r in $Reject) { if ($text -match $r) { $fail += "output has /$r/ (the command was not interrupted in time)" } }
        }
        Write-Host "--- $what ---" -ForegroundColor DarkGray
        Write-Host ($text.TrimEnd()) -ForegroundColor DarkGray
        if ($fail) { throw "$what FAILED: $($fail -join '; ')" }
        Write-Host "$what OK (exit code $code)" -ForegroundColor Green
    } finally {
        Remove-Item -LiteralPath $result -ErrorAction SilentlyContinue
    }
}
