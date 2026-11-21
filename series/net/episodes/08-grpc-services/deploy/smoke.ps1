<#
.SYNOPSIS
  Smoke test for episode 8 against the RUNNING API (start it first, see demo.md):
    REST + SignalR  http://localhost:5207  (HTTP/1.1)
    gRPC            http://localhost:5208  (HTTP/2 only)
  Uses the real console client (src/ProjectRequests.Cli, Grpc.Net.Client) for get / list / import, a real SignalR
  watcher to show that gRPC writes reach the live board too, and checks what happens when a client picks the wrong port.
  Expects an EMPTY database (delete src/ProjectRequests.Api/requests.db* and restart the API first).
#>
param(
    [string] $Rest = 'http://localhost:5207',
    [string] $Grpc = 'http://localhost:5208'
)
$ErrorActionPreference = 'Stop'
function Step([string] $text) { Write-Host "`n== $text" -ForegroundColor Cyan }
$cli = Join-Path $PSScriptRoot '../src/ProjectRequests.Cli'
$watcherProject = Join-Path $PSScriptRoot '../src/ProjectRequests.Watcher'
$sample = Join-Path $cli 'sample-import.csv'
$log = Join-Path ([IO.Path]::GetTempPath()) "mglab-ep08-watcher-$PID.log"
function Invoke-RequestsCli { & dotnet run --no-build --project $cli -- @args 2>&1 | ForEach-Object { "$_" } }

dotnet build $cli -v q -nologo | Out-Null
dotnet build $watcherProject -v q -nologo | Out-Null

Step '1. A SignalR watcher for FIN (episode 7), to see gRPC writes arrive on the live board'
$watcher = Start-Process dotnet -ArgumentList @('run', '--no-build', '--project', $watcherProject, '--', '--api', "$Rest/", '--department', 'FIN') `
    -RedirectStandardOutput $log -PassThru -NoNewWindow
$deadline = (Get-Date).AddSeconds(30)
while (-not ((Test-Path $log) -and (Select-String -Path $log -Pattern 'watching FIN' -Quiet))) {
    if ((Get-Date) -gt $deadline) { throw "watcher did not connect, see $log" }
    Start-Sleep -Milliseconds 300
}
'watcher connected'

Step '2. Client streaming: import sample-import.csv (7 lines: 3 good, 1 bad number, 3 rejected by the server)'
$import = Invoke-RequestsCli --address $Grpc import $sample
$import
"exit code (3 = some rows had errors): $LASTEXITCODE"

Step '3. Server streaming: list all, then FIN only'
Invoke-RequestsCli --address $Grpc list
Invoke-RequestsCli --address $Grpc list --department FIN

Step '4. Unary: get 2, get 99 (NotFound), get 0 (InvalidArgument)'
Invoke-RequestsCli --address $Grpc get 2
Invoke-RequestsCli --address $Grpc get 99
Invoke-RequestsCli --address $Grpc get 0

Step '5. Same data over REST: GET /api/requests'
$restList = Invoke-RestMethod -Uri "$Rest/api/requests"
"REST returns $(@($restList).Count) request(s)"

Step '6. What the watcher saw (the FIN row, pushed by the gRPC service through SignalR)'
Start-Sleep -Seconds 1
Stop-Process -Id $watcher.Id
Get-Content $log
"Watcher got the FIN import row: $([bool]((Get-Content $log) -match 'NEW     #\d+ FIN Standing desks'))"
"Watcher got an IT row:          $([bool]((Get-Content $log) -match ' IT '))   (expected False: other group)"
Remove-Item $log

Step '7. Wrong port: a gRPC client on the HTTP/1.1 endpoint, and HTTP/1.1 on the gRPC endpoint'
Invoke-RequestsCli --address $Rest get 1
$r = Invoke-WebRequest -Uri "$Grpc/healthz" -HttpVersion 1.1 -SkipHttpErrorCheck
"HTTP/1.1 request to the HTTP/2-only port: $($r.StatusCode)"

Step '8. A deadline that cannot be met (1 ms)'
Invoke-RequestsCli --address $Grpc --deadline 0.001 list
