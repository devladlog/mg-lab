# Demo shot list — DEVLADLOG .NET #5 Testing with xUnit & NUnit

Built and run in the container: `dotnet test` (MTP mode) 69 total, 67 passed, 2 skipped, three runs in a row.
Every mode of `deploy/Invoke-Tests.ps1` except `SqlServer` was run with `pwsh`; real output in `deploy/*.output.txt`.
**Needs the lab:** `sqlserver-lab` (CON-SQL01 from the Hyper-V lab). No Azure, no tenant, no licences.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host), VS Code + C# Dev Kit, PowerShell 7, .NET SDK 10.0.1xx, a browser. Screens 1–4 and 5 are all recorded here |
| CON-SQL01 (shared VM, exists) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.20.0.30. Only for screen 5 |
| SSMS on the host | Optional, for the second capture of screen 5 and for creating the login |
| Azure / M365 | Not used. Cost: €0 |

No other VM is needed. Nothing destructive: the tests create and drop their own `ProjectRequests_<framework>_<guid>`
databases on CON-SQL01.

## Prerequisites (once)
1. VS Code with the **C# Dev Kit** extension; open the folder `series/net/episodes/05-testing-with-xunit-nunit`.
   Learn documents Test Explorer support for MTP projects in VS Code; if the Testing view stays empty, build once
   (`dotnet build`) — tests don't appear before the first build.
2. Terminal (pwsh) in that folder:
   ```powershell
   dotnet tool restore           # ReportGenerator 5.6.1 (local tool)
   dotnet test                   # expect: total 69, succeeded 67, skipped 2
   ```
3. For screen 5 only — on CON-SQL01, signed in to SSMS as **lab Administrator** (or `sqlcmd` on the VM), create a
   test login that may create and drop databases. Type the password yourself; it is never written in a file:
   ```sql
   CREATE LOGIN requests_tests WITH PASSWORD = '<typed by the recorder>';
   ALTER SERVER ROLE dbcreator ADD MEMBER requests_tests;   -- create/alter/drop databases, nothing else
   ```

## Screens (match the `screen` scenes in script.yaml)

Terminal: dark theme, font ≥ 18 pt, window ~120 columns so the summary lines don't wrap. Before each terminal
capture run `Clear-Host`.

1. **`screens/test-explorer.jpg`** — *Both frameworks, one Test Explorer*
   - VS Code: Testing view (beaker icon) on the left, expand `ProjectRequests.Tests.NUnit` and
     `ProjectRequests.Tests.Xunit` one or two levels; click **Run Tests** at the top so all ticks are green
     (2 skipped, the SQL Server tests).
   - Bottom panel: `./deploy/Invoke-Tests.ps1` → `Test run summary: Passed!`, `total: 69`, `succeeded: 67`,
     `skipped: 2` (compare `deploy/all.output.txt`).
2. **`screens/two-failures.jpg`** — *Same bug, two failure messages*
   - Open `src/ProjectRequests.Api/Requests/PriorityRules.cs`, change `HighThreshold = 50_000m` to `49_000m`, save.
   - `./deploy/Invoke-Tests.ps1 -Mode Unit`. In frame: the NUnit block (`Expected: Standard` / `But was:  High`) and the
     xUnit block (`Assert.Equal() Failure: Values differ` / `Expected: Standard` / `Actual:   High`) and
     `total: 18`, `failed: 2` (compare `deploy/failure-messages.output.txt`). Scroll or crop the stack traces.
   - **Revert the change** (Ctrl+Z, save) and re-run `-Mode Unit` → 18 passed, before moving on.
3. **`screens/filter-gotcha.jpg`** — *Exit code 5, then the routed filter*
   - `./deploy/Invoke-Tests.ps1 -Mode FilterGotcha`. In frame: xUnit app `passed`, `total: 8`, then
     `Handshake failures:`, `Exit code: 5`, `Unknown option '--filter-trait'` under `ProjectRequests.Tests.NUnit.dll`.
   - Then `./deploy/Invoke-Tests.ps1 -Mode Unit` → both apps passed, `total: 18`. Two captures or one tall terminal.
   - The `--dotnet-test-pipe` path in the command line is a random local pipe name; crop it if distracting.
4. **`screens/coverage-report.jpg`** — *One coverage report for both frameworks*
   - `./deploy/Invoke-Tests.ps1 -Mode Coverage` (prints the summary and the path of `coverage-report/index.html`).
   - Open `coverage-report/index.html` in the browser. In frame: `Parser: MultiReport (2x Cobertura)`, line coverage
     ~93 %, branch ~89 % (container run: 93.4 % / 89.2 %), the class list with `PriorityRules` at 50 %.
   - Second capture: click `PriorityRules` → the two `const decimal` lines in red, both methods green.
5. **`screens/sqlserver-lab.jpg`** — *The same tests against SQL Server in the lab* (**needs CON-SQL01**)
   - Start the Hyper-V lab (`lab/hyperv/Start-MGLab.ps1`) and check `Test-NetConnection 10.20.0.30 -Port 1433`.
   - Off camera, in the pwsh terminal:
     ```powershell
     $env:REQUESTS_TEST_SQLSERVER = 'Server=10.20.0.30;User ID=requests_tests;Password=<typed>;TrustServerCertificate=True'
     Clear-Host
     ```
     (no `Database=`; the tests create their own. `TrustServerCertificate=True` because the lab instance uses its
     self-signed certificate.)
   - On camera: `./deploy/Invoke-Tests.ps1 -Mode SqlServer` → both apps passed, `total: 3` (xUnit 2, NUnit 1),
     `skipped: 0`.
   - Optional second capture: SSMS Object Explorer connected to CON-SQL01, refresh **Databases** during the run to
     catch a `ProjectRequests_xunit_…` or `ProjectRequests_nunit_…` database, refresh again after: gone.
   - **Masking:** the connection string must never be on screen (never `echo` the variable). If a test fails, the
     error can include the server name `10.20.0.30` — that's lab-internal and fine, but no password.
   - Not verified in the container (no SQL Server here). If it fails, report the error text; don't re-record with
     the tests disabled.

## Tear-down
```powershell
Remove-Item Env:REQUESTS_TEST_SQLSERVER
Remove-Item -Recurse -Force TestResults, coverage-report -ErrorAction SilentlyContinue
git checkout -- src/ProjectRequests.Api/Requests/PriorityRules.cs   # in case screen 2 wasn't reverted
```
On CON-SQL01 (SSMS as lab Administrator): check no `ProjectRequests_%` databases are left
(`SELECT name FROM sys.databases WHERE name LIKE 'ProjectRequests[_]%'`), then `DROP LOGIN requests_tests;`
unless episode 6+ needs it.
