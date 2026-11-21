<#
.SYNOPSIS
  Runs the three real services (Budget 5313, Requests 5312, Gateway 5311) as separate processes on real Kestrel and
  checks the whole story through the gateway: happy path, idempotency, a stopped service, recovery, a lost answer, one trace id.
  Needs: dotnet SDK 10 and a prior `dotnet build` of the solution. Works on Windows and Linux (PowerShell 7).
#>
param([string]$Configuration = 'Debug')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$logs = Join-Path ([IO.Path]::GetTempPath()) "ep11-smoke-$([guid]::NewGuid().ToString('N').Substring(0,6))"
New-Item -ItemType Directory $logs | Out-Null
$gw = 'http://localhost:5311'
$script:failed = 0
$script:procs = @{}

function Check([string]$what, [bool]$ok, [string]$detail = '') {
    if ($ok) { Write-Host "  PASS  $what $detail" } else { Write-Host "  FAIL  $what $detail"; $script:failed++ }
}

function Start-Svc([string]$name, [int]$port) {
    $dll = Join-Path $root "src/Contoso.$name/bin/$Configuration/net10.0/Contoso.$name.dll"
    if (-not (Test-Path $dll)) { throw "Build first: dotnet build (missing $dll)" }
    $env:ASPNETCORE_ENVIRONMENT = 'Development'
    $p = Start-Process dotnet -ArgumentList @($dll, '--urls', "http://localhost:$port") -WorkingDirectory (Join-Path $root "src/Contoso.$name") `
        -RedirectStandardOutput (Join-Path $logs "$name.log") -RedirectStandardError (Join-Path $logs "$name.err") -PassThru
    $script:procs[$name] = $p
    for ($i = 0; $i -lt 60; $i++) {
        try { if ((Invoke-WebRequest "http://localhost:$port/alive" -SkipHttpErrorCheck -TimeoutSec 2).StatusCode -eq 200) { return } } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "$name did not start on $port. See $logs"
}

function Stop-Svc([string]$name) {
    $p = $script:procs[$name]
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force; $p.WaitForExit() }
}

function Post([string]$body, [hashtable]$headers = @{}) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-WebRequest "$gw/api/requests" -Method Post -Body $body -ContentType 'application/json' -Headers $headers -SkipHttpErrorCheck
    [pscustomobject]@{ Status = [int]$r.StatusCode; Body = ($r.Content | ConvertFrom-Json); Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1); Headers = $r.Headers }
}
function Budget([string]$dept) { Invoke-RestMethod "$gw/api/budgets/$dept" }
function NewBody([string]$dept, [int]$amount, [string]$title) { (@{ title = $title; departmentCode = $dept; amount = $amount; requestedBy = 'alex.demo@contoso.com' } | ConvertTo-Json) }

try {
    Remove-Item (Join-Path $root 'src/Contoso.Requests.Service/requests.db*') -ErrorAction SilentlyContinue
    Write-Host "Starting Budget, Requests, Gateway (logs in $logs)"
    Start-Svc 'Budget.Service' 5313; Start-Svc 'Requests.Service' 5312; Start-Svc 'Gateway' 5311

    Write-Host "`n1. Happy path through the gateway"
    $a = Post (NewBody 'FIN' 12000 'Standing desks')
    Check 'POST /api/requests -> 201 Reserved' ($a.Status -eq 201 -and $a.Body.budgetState -eq 'Reserved') "($($a.Status) $($a.Body.budgetState), $($a.Seconds)s)"
    Check 'Budget service shows 12,000 reserved for FIN' ((Budget 'FIN').reserved -eq 12000)
    $health = Invoke-RestMethod "$gw/health/services"
    Check 'Gateway /health/services is Healthy' ($health.status -eq 'Healthy')

    Write-Host "`n2. Same Idempotency-Key twice"
    $key = [guid]::NewGuid().ToString()
    $first = Post (NewBody 'OPS' 3000 'Whiteboards') @{ 'Idempotency-Key' = $key }
    $second = Post (NewBody 'OPS' 3000 'Whiteboards') @{ 'Idempotency-Key' = $key }
    Check 'first 201, second 200 with the same id' ($first.Status -eq 201 -and $second.Status -eq 200 -and $first.Body.id -eq $second.Body.id) "(ids $($first.Body.id)/$($second.Body.id))"
    Check 'OPS reserved once (3,000)' ((Budget 'OPS').reserved -eq 3000)

    Write-Host "`n3. One trace id across three processes"
    $trace = $a.Body.traceId
    $hits = 'Gateway', 'Requests.Service', 'Budget.Service' | ForEach-Object { (Select-String -Path (Join-Path $logs "$_.log") -Pattern $trace -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count }
    Check "trace id $trace appears in the gateway, requests and budget logs" (($hits | Where-Object { $_ -gt 0 }).Count -eq 3) "(line counts: $($hits -join ', '))"

    Write-Host "`n4. Budget service stopped"
    Stop-Svc 'Budget.Service'
    $b = Post (NewBody 'IT' 9000 'Laptops for the lab')
    Check 'POST -> 202 Pending after the retries' ($b.Status -eq 202 -and $b.Body.budgetState -eq 'Pending') "($($b.Status) $($b.Body.budgetState), $($b.Seconds)s)"
    $c = Post (NewBody 'IT' 1000 'Cables')
    Check 'next POST -> 202 Pending, fast (circuit open)' ($c.Status -eq 202 -and $c.Seconds -lt 1.5) "($($c.Status), $($c.Seconds)s)"
    $health = Invoke-RestMethod "$gw/health/services"
    Check 'Gateway /health/services is Degraded, budget not reachable' ($health.status -eq 'Degraded' -and $health.services.budget.status -eq 'Degraded')
    Check 'GET /api/requests still works through the gateway' ((Invoke-RestMethod "$gw/api/requests").Count -ge 4)
    $r = Invoke-WebRequest "$gw/api/budgets/FIN" -SkipHttpErrorCheck
    Check 'GET /api/budgets/FIN -> 502 (the gateway cannot reach it)' ([int]$r.StatusCode -eq 502) "($([int]$r.StatusCode))"
    Check 'Requests /health is still Healthy' ((Invoke-WebRequest 'http://localhost:5312/health').Content -eq 'Healthy')

    Write-Host "`n5. Budget service back: the re-check worker finishes the pending requests (up to ~30 s)"
    Start-Svc 'Budget.Service' 5313
    $done = $false
    for ($i = 0; $i -lt 40 -and -not $done; $i++) {
        Start-Sleep -Seconds 1
        $states = (Invoke-RestMethod "$gw/api/requests") | Where-Object { $_.id -in $b.Body.id, $c.Body.id } | ForEach-Object budgetState
        $done = ($states | Where-Object { $_ -eq 'Reserved' }).Count -eq 2
    }
    Check 'both pending requests are Reserved' $done "(after ~$i s)"
    Check 'IT reserved 10,000 (9,000 + 1,000), once each' ((Budget 'IT').reserved -eq 10000)

    Write-Host "`n6. A lost answer (fault injection): the reservation is made, the answer is lost twice"
    Stop-Svc 'Budget.Service'
    $env:Faults__FailFirstAttemptsPerKey = '2'; $env:Faults__FailAfterCommit = 'true'
    Start-Svc 'Budget.Service' 5313
    Remove-Item Env:Faults__FailFirstAttemptsPerKey, Env:Faults__FailAfterCommit
    Start-Sleep -Seconds 16   # let the circuit from step 4 close (break duration 15 s)
    $d = Post (NewBody 'FIN' 5000 'Monitors')
    Check 'POST -> 201 Reserved after two lost answers' ($d.Status -eq 201 -and $d.Body.budgetState -eq 'Reserved') "($($d.Status) $($d.Body.budgetState), $($d.Seconds)s)"
    Check 'FIN reserved exactly 5,000 (not 15,000)' ((Budget 'FIN').reserved -eq 5000) "(budget restarted: its ledger is in memory)"
    $attempts = (Select-String -Path (Join-Path $logs 'Budget.Service.log') -Pattern 'Fault injection: reservation made' | Measure-Object).Count
    Check 'the Budget service logged the two lost answers' ($attempts -eq 2) "($attempts)"
}
finally {
    foreach ($n in @($script:procs.Keys)) { Stop-Svc $n }
    Remove-Item (Join-Path $root 'src/Contoso.Requests.Service/requests.db*') -ErrorAction SilentlyContinue
}
Write-Host ""
if ($script:failed -gt 0) { Write-Host "$script:failed check(s) failed. Logs: $logs"; exit 1 }
Write-Host "All checks passed."; Remove-Item $logs -Recurse -Force
