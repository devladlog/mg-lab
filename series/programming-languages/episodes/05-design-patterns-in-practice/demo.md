# Demo shot list — DEVLADLOG Code #5 Design patterns in practice

Everything was built and tested in the container (`dotnet test`: **27 passed**, 5 runs in a row;
`./demo/run-all.sh`: exit code 0). Every screen is the real console app (Generic Host + built-in DI) running on the
recording laptop against the real sample files; nothing is mocked. Reference output:
[`demo/expected-output.txt`](demo/expected-output.txt).

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). **No VM, no tenant, no Azure resources.** | — |
| .NET SDK 10.0.1xx | `dotnet --version` (built and tested with 10.0.115) | free |
| NuGet access | first restore downloads `Microsoft.Extensions.Hosting` / `Options.DataAnnotations` 10.0.15 + xUnit | free |
| Windows Terminal + PowerShell 7 | dark theme, font 18 pt or larger, ~150 columns (the route lines are ~120 characters) | free |
| VS Code + C# Dev Kit | optional B-roll of `ServiceCollectionExtensions.cs` (the composition root) | free |

## Setup (once, before recording)
```powershell
cd series\programming-languages\episodes\05-design-patterns-in-practice
dotnet test DesignPatterns.slnx -m:1                 # expect Passed: 27 (restores and builds everything)
dotnet build src\Contoso.Approvals.Patterns.Cli -m:1
Remove-Item Env:DOTNET_ENVIRONMENT -ErrorAction SilentlyContinue   # the Production screens rely on the default
function prompt { '> ' }                             # short prompt: no user name or path on screen
$Host.UI.RawUI.WindowTitle = 'approvals'
cls
```
Run each command below once as a rehearsal (JIT warm-up), then `cls` before each capture. The app writes
`outbox\PR-*.txt` in the current folder (overwritten on every run, git-ignored).

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/run.jpg`** — *Eight requests, two batches, three routes* (scene `run`)
   - `dotnet run --no-build --project src\Contoso.Approvals.Patterns.Cli`
   - Frame: header with `environment: Production | High >= 50,000 EUR | Board >= 250,000 EUR`,
     `routes (strategy): board, high, standard`, both batches (PR-2026-0103 `Finance: Sam Demo -> Board: Taylor Demo`,
     `! justification required for board requests` under PR-2026-0106), `audit trail (scoped): 4 entries [ok]` twice,
     and the summary: `13 lookups, 10 file reads, 3 from cache`, `8 notification files in ./outbox`, the tally.
   - Optional B-roll: `code outbox\PR-2026-0103.txt` (`To: Sam Demo (Finance)`).

2. **`screens/options.jpg`** — *A bad policy never starts* (scene `optionsrun`)
   - `dotnet run --no-build --project src\Contoso.Approvals.Patterns.Cli -- --Policy:BoardThreshold=10000`
   - then `$LASTEXITCODE` → `1`
   - Frame: the host's `fail: Microsoft.Extensions.Hosting.Internal.Host[11]` / `Hosting failed to start` /
     `OptionsValidationException: Policy:BoardThreshold must be greater than Policy:HighThreshold.` at the top and
     `Startup failed in Production: OptionsValidationException` + `1` at the bottom. If the stack trace pushes the top
     out of view, take two frames (top and bottom) and let the editor stack them.

3. **`screens/captive-prod.jpg`** — *Production: exit code zero, empty audit* (scene `captiveprod`)
   - `dotnet run --no-build --project src\Contoso.Approvals.Patterns.Cli -- --Demo:CaptiveAudit=true`
   - then `$LASTEXITCODE` → `0`
   - Frame: `environment: Production`, the eight routed requests, and `audit trail (scoped): 0 entries
     [MISSING, expected 4]` under each batch.

4. **`screens/captive-dev.jpg`** — *Development: the container refuses* (scene `captivedev`)
   - `dotnet run --no-build --project src\Contoso.Approvals.Patterns.Cli -- --Demo:CaptiveAudit=true --environment Development`
   - Frame: `Startup failed in Development: AggregateException` and the wrapped message containing
     `Cannot consume scoped service 'Contoso.Approvals.Patterns.Events.AuditTrail' from singleton
     'Contoso.Approvals.Patterns.Events.IRequestObserver'`.

The code scenes (`strategy`, `catalog`, `decorator`, `chain`, `observer`, `options`, `gotcha`, `tests`) are slides
with excerpts from `src/` and `tests/`. Their proof is the screens above plus the tests
`Decorator_order_changes_what_you_measure`, `Only_the_outer_decorator_is_resolvable_without_a_key`,
`Gotcha_resolving_one_observer_silently_gives_you_the_last_registration`,
`Gotcha_captive_dependency_in_Production_runs_and_loses_the_audit` and
`Gotcha_captive_dependency_in_Development_fails_at_build`. Optional B-roll: VS Code Test Explorer showing 27 green tests.

(Git Bash/WSL alternative for a rehearsal: `./demo/run-all.sh` runs all four modes with ok/FAIL checks.)

## Masking
- Short prompt and window title as above. All data is fictional (`PR-2026-01xx`, Contoso departments, `<First> Demo`
  approvers, which match the lab's fictional user names but are only strings in a JSON file). Nothing to blur.
- No paths appear in the normal output. If a build error ever shows a full path with a user name, record from a
  neutral folder (e.g. `C:\lab\mg-lab\...`) or crop.

## Tear-down
- `Remove-Item -Recurse outbox`
- `Get-ChildItem -Recurse -Directory -Include bin,obj | Remove-Item -Recurse -Force`
- If `DOTNET_ENVIRONMENT` was set for anything else, restore it. Nothing was created outside the folder.
