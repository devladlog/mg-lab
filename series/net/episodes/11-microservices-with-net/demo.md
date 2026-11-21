# Demo shot list — DEVLADLOG .NET #11 Microservices with .NET

Built and run in the container (Linux): `dotnet test` 30 total, 30 passed; `deploy/smoke.ps1` 17 checks on three real Kestrel
processes (output in `deploy/smoke.output.txt`): request through the gateway, idempotency key replay, one trace id in all three logs,
Budget stopped (202 Pending, circuit open, gateway Degraded, 502 on the budget route), Budget restarted (re-check worker), and a lost
answer (fault injection). **Not verified in the container:** the same commands on Windows (`curl.exe`, Windows Terminal, `Tee-Object`).
If something behaves differently, report it instead of re-scripting around it. No Azure, no tenant, no VM, no licences. Cost: nothing.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host): .NET SDK 10.0.1xx, VS Code (C# Dev Kit), PowerShell 7, Windows Terminal, `curl.exe`. All five screens are recorded here |
| Network | localhost only: gateway `http://localhost:5311`, requests service `5312`, budget service `5313`. Ports must be free. The 10.50.0.0/24 lab network is not used |
| Hyper-V lab / Azure / M365 | Not used |

## Setup (before recording)
```powershell
cd series/net/episodes/11-microservices-with-net
dotnet test                                    # expect total 30, succeeded 30
dotnet build Contoso.Microservices.slnx
New-Item -ItemType Directory $env:TEMP\ep11logs -Force | Out-Null
Remove-Item src/Contoso.Requests.Service/requests.db* -ErrorAction SilentlyContinue   # ids start at 1

# Windows Terminal, four panes. Start Budget first, then Requests, then the gateway. Each line also writes a log file for the trace id search.
# pane 1 (budget)   cd src/Contoso.Budget.Service;   dotnet run --launch-profile http 2>&1 | Tee-Object $env:TEMP\ep11logs\budget.log
# pane 2 (requests) cd src/Contoso.Requests.Service; dotnet run --launch-profile http 2>&1 | Tee-Object $env:TEMP\ep11logs\requests.log
# pane 3 (gateway)  cd src/Contoso.Gateway;          dotnet run --launch-profile http 2>&1 | Tee-Object $env:TEMP\ep11logs\gateway.log
# pane 4 (client)   the commands below
```
**Warm up** with one throw-away request and the health page (the very first call can take several seconds), then stop the three
services, delete `requests.db*`, and start them again so the recording begins with an empty database. Terminal font size 16+.

The client commands (pane 4), PowerShell 7:
```powershell
$gw = 'http://localhost:5311'
function Req($dept, $amount, $title) { Invoke-WebRequest "$gw/api/requests" -Method Post -ContentType 'application/json' -SkipHttpErrorCheck `
    -Body (@{ title=$title; departmentCode=$dept; amount=$amount; requestedBy='alex.demo@contoso.com' } | ConvertTo-Json) }
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/gateway-calls.jpg`** — *One front door, three processes*
   - `$r = Req FIN 12000 'Standing desks'; $r.StatusCode; $r.Content` → `201`, `"budgetState":"Reserved"`, a `traceId`.
   - `Invoke-RestMethod "$gw/api/budgets/FIN"` → reserved 12000, remaining 38000. `Invoke-RestMethod "$gw/health/services"` → `Healthy`.
   - Trace: `$t = ($r.Content | ConvertFrom-Json).traceId; Select-String -Path $env:TEMP\ep11logs\*.log -Pattern $t -SimpleMatch`
     → matches in `gateway.log`, `requests.log` and `budget.log` (smoke run: 2, 4 and 2 lines).
2. **`screens/budget-down.jpg`** — *Stop the Budget service*
   - Ctrl+C in pane 1. `Measure-Command { $b = Req IT 9000 'Laptops for the lab' }` then `$b.StatusCode` → `202`, `budgetState: Pending`
     (about 0.7-2 s: retries, and the breaker opening). Second call `Req IT 1000 'Cables'` → `202`, under half a second.
   - `Invoke-RestMethod "$gw/health/services"` → `Degraded`, budget "not reachable". `Invoke-RestMethod "$gw/api/requests"` still lists the requests.
     `Invoke-WebRequest "$gw/api/budgets/FIN" -SkipHttpErrorCheck` → `502`. `curl.exe http://localhost:5312/health` → `Healthy`.
   - Pane 2 (requests): the `Polly` retry warnings, `OnCircuitOpened`, `Circuit to the Budget service is open: failing fast, the request stays pending`.
3. **`screens/recovery.jpg`** — *Budget is back*
   - Pane 1: start the Budget service again (same command). Within about 15 s pane 2 logs `Re-check: request 2 is now Reserved` and request 3.
   - `Invoke-RestMethod "$gw/api/requests"` → all `Reserved`; `Invoke-RestMethod "$gw/api/budgets/IT"` → reserved 10000 (the Budget ledger is in memory, so it only
     knows the two re-checked reservations: 9,000 + 1,000).
4. **`screens/lost-answer.jpg`** — *The lost answer* (fault injection: demo only, both settings are off by default)
   - Ctrl+C in pane 1, then: `$env:Faults__FailFirstAttemptsPerKey='2'; $env:Faults__FailAfterCommit='true'; cd src/Contoso.Budget.Service; dotnet run --launch-profile http`,
     then `Remove-Item Env:Faults__*`. Wait about 15 s (the circuit from screen 2 closes).
   - `$d = Req FIN 5000 'Monitors'; $d.StatusCode; $d.Content` → `201`, `Reserved`. Pane 1: two `Fault injection: reservation made (Created), answer for attempt N is lost`
     lines, then the replay. `Invoke-RestMethod "$gw/api/budgets/FIN"` → reserved 5000 (the restarted ledger started empty), not 15000.
5. **`screens/tests.jpg`** — *Real services, in memory*
   - VS Code terminal in the episode folder: `Clear-Host; dotnet test` → total 30, succeeded 30. Compare `deploy/tests.output.txt`.
   - Optional: Testing view with `BudgetServiceTests`, `RequestsServiceTests`, `RetryRuleTests` and `GatewayTests` expanded.

## Masking
Nothing to mask: fictional names only (`alex.demo@contoso.com`), localhost addresses, no tenant, no tokens.

## Tear-down
Ctrl+C in the three panes; `Remove-Item src/Contoso.Requests.Service/requests.db*`; `Remove-Item $env:TEMP\ep11logs -Recurse`;
`Remove-Item Env:Faults__* -ErrorAction SilentlyContinue`. Nothing else was created.
