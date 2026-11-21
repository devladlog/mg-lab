<#
.SYNOPSIS
  Episode 9 demo driver: starts the API three ways and load-tests it with the loadtest tool, so the numbers on screen
  come from the real app. Works on Windows PowerShell 7 and on Linux/macOS pwsh.

.DESCRIPTION
  1. BEFORE  : /api/slow/requests (N+1, tracked entities)
  2. AFTER   : /api/requests with the output cache OFF   (Perf__ListCache=false)
  3. CACHED  : /api/requests with the output cache ON    (the default)
  Builds in Release once, runs the API from the built dll (so the SQLite file lives in a temp folder), and always
  stops the API at the end.
#>
param(
    [int]$Seconds = 8,
    [int]$Concurrency = 8,
    [int]$Take = 100,
    [int]$Port = 5209
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root 'src/ProjectRequests.Perf.Api'
$load = Join-Path $root 'src/ProjectRequests.Perf.LoadTest'
$db = Join-Path ([IO.Path]::GetTempPath()) "perf-demo-$PID.db"
$base = "http://localhost:$Port"

dotnet build $api -c Release --nologo -v quiet | Out-Null
dotnet build $load -c Release --nologo -v quiet | Out-Null
$apiDll = Join-Path $api 'bin/Release/net10.0/ProjectRequests.Perf.Api.dll'
$loadDll = Join-Path $load 'bin/Release/net10.0/loadtest.dll'

function Start-Api([string]$listCache) {
    Remove-Item "$db*" -Force -ErrorAction SilentlyContinue
    $env:ASPNETCORE_ENVIRONMENT = 'Development'          # enables the slow endpoint (Perf:EnableSlowEndpoint)
    $env:ASPNETCORE_URLS = $base
    $env:ConnectionStrings__Requests = "Data Source=$db"
    $env:Perf__ListCache = $listCache
    $p = Start-Process dotnet -ArgumentList @($apiDll) -WorkingDirectory $api -PassThru -RedirectStandardOutput ([IO.Path]::GetTempFileName()) -RedirectStandardError ([IO.Path]::GetTempFileName())
    for ($i = 0; $i -lt 60; $i++) {                       # 20,000 rows are seeded on first start
        Start-Sleep -Milliseconds 500
        try { Invoke-RestMethod "$base/api/requests?pageSize=1" | Out-Null; return $p } catch { }
    }
    Stop-Process $p -Force
    throw 'API did not start'
}

function Invoke-Load([string]$title, [string]$url) {
    Write-Host "`n=== $title" -ForegroundColor Cyan
    dotnet $loadDll $url --concurrency $Concurrency --seconds $Seconds --warmup 2
}

try {
    $p = Start-Api 'false'
    Invoke-Load "BEFORE: N+1, tracked entities (take=$Take)" "$base/api/slow/requests?take=$Take"
    Invoke-Load "AFTER: projection + paging, output cache off" "$base/api/requests?department=FIN&pageSize=$Take"
    Stop-Process $p -Force; $p = $null

    $p = Start-Api 'true'
    Invoke-Load "AFTER + output cache on" "$base/api/requests?department=FIN&pageSize=$Take"
}
finally {
    if ($p) { Stop-Process $p -Force -ErrorAction SilentlyContinue }
    Remove-Item "$db*" -Force -ErrorAction SilentlyContinue
}
