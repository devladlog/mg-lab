<#
.SYNOPSIS
  Smoke test for episode 7 against the RUNNING apps (start them first, see demo.md):
    API  http://localhost:5207  (src/ProjectRequests.Api,  dotnet run --launch-profile http)
    Web  http://localhost:5180  (src/ProjectRequests.Web,  dotnet run --launch-profile http)
  Starts the console watcher (a real SignalR client, WebSockets) for FIN, creates and decides requests through the
  REST API, and shows what the watcher received. Then checks the hub's negotiate, its CORS preflight and /live.
#>
param(
    [string] $Api = 'http://localhost:5207',
    [string] $Web = 'http://localhost:5180'
)
$ErrorActionPreference = 'Stop'
function Step([string] $text) { Write-Host "`n== $text" -ForegroundColor Cyan }
$watcherProject = Join-Path $PSScriptRoot '../src/ProjectRequests.Watcher'
$log = Join-Path ([IO.Path]::GetTempPath()) "mglab-ep07-watcher-$PID.log"

Step '1. Watcher for FIN (a .NET console SignalR client)'
dotnet build $watcherProject -v q -nologo | Out-Null
$watcher = Start-Process dotnet -ArgumentList @('run', '--no-build', '--project', $watcherProject, '--', '--api', "$Api/", '--department', 'FIN') `
    -RedirectStandardOutput $log -PassThru -NoNewWindow
$deadline = (Get-Date).AddSeconds(30)
while (-not ((Test-Path $log) -and (Select-String -Path $log -Pattern 'watching FIN' -Quiet))) {
    if ((Get-Date) -gt $deadline) { throw "watcher did not connect, see $log" }
    Start-Sleep -Milliseconds 300
}
"watcher connected"

Step '2. Two requests (IT, FIN) and a decision on the FIN one, through the REST API'
$created = foreach ($body in @(
        @{ title = 'Data platform';  budget = 80000; requestedBy = 'alex.demo@contoso.com'; departmentCode = 'IT' },
        @{ title = 'Laptop refresh'; budget = 12000; requestedBy = 'alex.demo@contoso.com'; departmentCode = 'FIN' })) {
    Invoke-RestMethod -Method Post -Uri "$Api/api/requests" -ContentType 'application/json' -Body ($body | ConvertTo-Json)
}
$fin = $created[1]
$decision = @{ approve = $true; decidedBy = 'sam.demo@contoso.com'; version = $fin.version } | ConvertTo-Json
$null = Invoke-RestMethod -Method Post -Uri "$Api/api/requests/$($fin.id)/decision" -ContentType 'application/json' -Body $decision
Start-Sleep -Seconds 2
Stop-Process -Id $watcher.Id
Get-Content $log
$lines = Get-Content $log
"Watcher got FIN create:    $([bool]($lines -match "NEW     #$($fin.id) FIN"))"
"Watcher got FIN decision:  $([bool]($lines -match "UPDATED #$($fin.id) FIN.*Approved"))"
"Watcher got the IT one:    $([bool]($lines -match "#$($created[0].id) IT"))   (expected False: other group)"
Remove-Item $log

Step '3. Hub negotiate (what every client does first)'
$neg = Invoke-RestMethod -Method Post -Uri "$Api/hubs/requests/negotiate?negotiateVersion=1"
"negotiateVersion: $($neg.negotiateVersion); transports: $(($neg.availableTransports | ForEach-Object transport) -join ', ')"

Step '4. CORS preflight for the hub, as the browser sends it from the Blazor app'
$pre = Invoke-WebRequest -Method Options -Uri "$Api/hubs/requests/negotiate?negotiateVersion=1" -SkipHttpErrorCheck -Headers @{
    Origin = $Web; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'x-requested-with,x-signalr-user-agent' }
"$($pre.StatusCode) Allow-Origin: $($pre.Headers['Access-Control-Allow-Origin']) Allow-Credentials: $($pre.Headers['Access-Control-Allow-Credentials']) Allow-Methods: $($pre.Headers['Access-Control-Allow-Methods'])"

Step '5. /live - WebAssembly page, prerendered, not connected yet'
$live = (Invoke-WebRequest -Uri "$Web/live").Content
"WebAssembly component marker: $($live -match '"type":"webassembly"')"
"Not connected during prerender: $($live -match 'waiting for the page to become interactive')"
