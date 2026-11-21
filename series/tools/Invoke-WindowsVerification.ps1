#Requires -Version 5.1
<#
.SYNOPSIS
  Runs every category-series episode's offline test suites on Windows and writes a results report.
.DESCRIPTION
  Read-only for the episodes: it only builds and tests them. No sign-ins, no cloud calls, no git.
  .NET test projects run with `dotnet test`; Pester suites run in PowerShell 7 (pwsh) and, with
  -AlsoWindowsPowerShell, in Windows PowerShell 5.1 too. Python/Node suites are skipped unless asked
  (they already pass on Linux and would install packages).
  Results: <Root>\verify-results\results.json and summary.md (rewritten after every suite, so a
  partial run is still readable).
.EXAMPLE
  .\series\tools\Invoke-WindowsVerification.ps1                      # everything
  .\series\tools\Invoke-WindowsVerification.ps1 -Series windows-server,net
#>
[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string[]]$Series,
    [int]$TimeoutMinutes = 15,
    [switch]$AlsoWindowsPowerShell,
    [switch]$IncludePython,
    [switch]$IncludeNode,
    [switch]$RerunFailed,          # only the episodes that did not pass in verify-results\results.json
    [string]$OutName = 'verify-results'
)
$ErrorActionPreference = 'Stop'
$flagFile = Join-Path $Root 'verify-results\rerun-failed.flag'
$onlyEpisodes = @()
if (Test-Path $flagFile) {
    $RerunFailed = $true
    $onlyEpisodes = @(Get-Content $flagFile | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    Write-Host ("rerun-failed.flag found: running " + $(if ($onlyEpisodes) { $onlyEpisodes -join ', ' } else { 'only the episodes that failed last time' })) -ForegroundColor Yellow
}
$out = Join-Path $Root $OutName
$previous = @()
if ($RerunFailed) {
    $prevFile = Join-Path $Root 'verify-results\results.json'
    if (Test-Path $prevFile) { $previous = @((Get-Content $prevFile -Raw | ConvertFrom-Json) | Where-Object status -ne 'pass' | ForEach-Object episode | Sort-Object -Unique) }
    if (-not $OutName -or $OutName -eq 'verify-results') { $out = Join-Path $Root 'verify-results-rerun' }
}
New-Item -ItemType Directory -Force -Path $out, (Join-Path $out 'logs') | Out-Null
$results = [System.Collections.Generic.List[object]]::new()

function Get-Tool([string]$name) { (Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
# Bicep: many template tests call `bicep`. Use a PATH copy, else the Azure CLI's managed copy (install it if missing).
if (-not (Get-Tool bicep)) {
    $azBicepDir = Join-Path $env:USERPROFILE '.azure\bin'
    if (-not (Test-Path (Join-Path $azBicepDir 'bicep.exe')) -and (Get-Tool az)) { & az bicep install 2>&1 | Out-Host }
    if (Test-Path (Join-Path $azBicepDir 'bicep.exe')) { $env:PATH = "$azBicepDir;$env:PATH"; Write-Host "Using Bicep from $azBicepDir" -ForegroundColor Yellow }
}
$dotnet = Get-Tool dotnet; $pwsh = Get-Tool pwsh; $winps = Get-Tool powershell; $python = Get-Tool python; $npm = Get-Tool npm

function Invoke-Suite {
    param([string]$Episode, [string]$Kind, [string]$WorkDir, [string]$Exe, [string[]]$ArgList)
    $safe = ("$Episode" + '__' + "$Kind") -replace '[\\/:*?"<>| ]', '_'
    if ($safe.Length -gt 150) { $safe = $safe.Substring(0, 150) }
    $log = Join-Path $out "logs\$safe.log"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Write-Host ("[{0:HH:mm:ss}] {1} :: {2}" -f (Get-Date), $Episode, $Kind) -ForegroundColor Cyan
    $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -WorkingDirectory $WorkDir -NoNewWindow -PassThru `
        -RedirectStandardOutput "$log.out" -RedirectStandardError "$log.err"
    $finished = $p.WaitForExit($TimeoutMinutes * 60 * 1000)
    if (-not $finished) { try { $p.Kill($true) } catch { try { $p.Kill() } catch {} } }
    $sw.Stop()
    $text = ((Get-Content "$log.out" -Raw -ErrorAction SilentlyContinue) + "`n" + (Get-Content "$log.err" -Raw -ErrorAction SilentlyContinue))
    Set-Content -Path $log -Value $text -Encoding utf8
    Remove-Item "$log.out", "$log.err" -ErrorAction SilentlyContinue
    $status = if (-not $finished) { 'timeout' } elseif ($p.ExitCode -eq 0) { 'pass' } else { 'fail' }
    $tail = ($text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 25) -join "`n"
    $r = [pscustomobject]@{
        episode = $Episode; kind = $Kind; status = $status; exit = $(if ($finished) { $p.ExitCode } else { $null })
        seconds = [math]::Round($sw.Elapsed.TotalSeconds); command = "$Exe $($ArgList -join ' ')"; dir = $WorkDir; tail = $tail
    }
    $results.Add($r)
    Write-Host ("    -> {0} ({1}s)" -f $status, $r.seconds) -ForegroundColor $(if ($status -eq 'pass') { 'Green' } else { 'Red' })
    Save-Report
    return $r
}

function Save-Report {
    $results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'results.json') -Encoding utf8
    $lines = @("# Windows verification", "", "Machine: $env:COMPUTERNAME  ", "Run: $(Get-Date -Format 's')  ",
        "dotnet: $(if ($dotnet) { (& $dotnet --version) } else { 'missing' })  ", "pwsh: $(if ($pwsh) { 'yes' } else { 'missing' })", "",
        "| Status | Episode | Suite | Seconds |", "|---|---|---|---|")
    foreach ($r in $results) { $lines += "| $($r.status) | $($r.episode) | $($r.kind) | $($r.seconds) |" }
    $fails = $results | Where-Object status -ne 'pass'
    if ($fails) {
        $lines += "", "## Not passing", ""
        foreach ($f in $fails) { $lines += "### $($f.episode) :: $($f.kind) ($($f.status))", '```', $f.tail, '```', "" }
    }
    $lines | Set-Content (Join-Path $out 'summary.md') -Encoding utf8
}

$skip = '\\(bin|obj|node_modules|\.venv|venv|\.git|reference|naive|legacy)\\'
$episodes = Get-ChildItem (Join-Path $Root 'series\*\episodes\*') -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName 'script.yaml') } |
    Where-Object { -not $Series -or ($Series -contains $_.Parent.Parent.Name) } |
    Where-Object { -not $RerunFailed -or ($(if ($onlyEpisodes) { $onlyEpisodes } else { $previous }) -contains "$($_.Parent.Parent.Name)/$($_.Name)") } |
    Sort-Object FullName

foreach ($ep in $episodes) {
    $name = "$($ep.Parent.Parent.Name)/$($ep.Name)"

    if ($dotnet) {
        $projects = Get-ChildItem $ep.FullName -Recurse -Filter *.csproj -File |
            Where-Object { $_.FullName -notmatch $skip } |
            Where-Object { (Get-Content $_.FullName -Raw) -match 'xunit|nunit|MSTest|Microsoft\.NET\.Test\.Sdk|TUnit' }
        foreach ($proj in $projects) {
            $rel = $proj.FullName.Substring($ep.FullName.Length + 1)
            $r = Invoke-Suite $name "dotnet:$rel" $proj.DirectoryName $dotnet @('test', "`"$($proj.FullName)`"", '-m:1', '--nologo')
            if ($r.status -eq 'fail' -and $r.tail -match '--project|-m:1|MSB1001|Microsoft\.Testing\.Platform') {
                $null = $results.Remove($r)
                Invoke-Suite $name "dotnet-mtp:$rel" $proj.DirectoryName $dotnet @('test', '--project', "`"$($proj.FullName)`"") | Out-Null
            }
        }
    }

    $pester = Get-ChildItem $ep.FullName -Recurse -Filter *.Tests.ps1 -File | Where-Object { $_.FullName -notmatch $skip }
    if ($pester) {
        $dirs = $pester.DirectoryName | Sort-Object -Unique
        $paths = ($dirs | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ','
        $localMods = Join-Path $Root '.tools\Modules'
        $cmd = "`$ErrorActionPreference='Stop'; if (Test-Path '$localMods') { `$env:PSModulePath = '$localMods' + [IO.Path]::PathSeparator + `$env:PSModulePath }; Import-Module Pester -MinimumVersion 5.0; `$c = New-PesterConfiguration; `$c.Run.Path = @($paths); `$c.Run.Exit = `$true; `$c.Output.Verbosity = 'Normal'; Invoke-Pester -Configuration `$c"
        $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
        if ($pwsh) { Invoke-Suite $name 'pester:pwsh7' $ep.FullName $pwsh @('-NoProfile', '-NonInteractive', '-EncodedCommand', $enc) | Out-Null }
        $needs7 = Get-ChildItem $ep.FullName -Recurse -Include *.ps1, *.psm1 -File | Where-Object { $_.FullName -notmatch $skip } |
            Select-String -Pattern '#Requires\s+-Version\s+7|-PSEdition\s+Core' -List | Select-Object -First 1
        if ($AlsoWindowsPowerShell -and $winps -and -not $needs7) { Invoke-Suite $name 'pester:winps51' $ep.FullName $winps @('-NoProfile', '-NonInteractive', '-EncodedCommand', $enc) | Out-Null }
    }

    if ($IncludePython -and $python -and (Test-Path (Join-Path $ep.FullName 'tests'))) {
        if (Get-ChildItem (Join-Path $ep.FullName 'tests') -Recurse -Filter 'test_*.py' -File) {
            Invoke-Suite $name 'pytest' $ep.FullName $python @('-m', 'pytest', '-q', 'tests') | Out-Null
        }
    }
    if ($IncludeNode -and $npm) {
        Get-ChildItem $ep.FullName -Recurse -Filter package.json -File | Where-Object { $_.FullName -notmatch $skip } |
            Where-Object { (Get-Content $_.FullName -Raw) -match '"test"\s*:' } | ForEach-Object {
                Invoke-Suite $name "npm:$($_.Directory.Name)" $_.DirectoryName $npm @('test') | Out-Null
            }
    }
}
Save-Report
$p = ($results | Where-Object status -eq 'pass').Count
Write-Host "`nDone: $p of $($results.Count) suites passed. Report: $out\summary.md" -ForegroundColor Yellow
