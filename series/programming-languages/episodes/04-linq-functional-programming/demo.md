# Demo shot list — DEVLADLOG Code #4 LINQ and functional C#

Everything was built and tested in the container (`dotnet test`: **34 passed**, 5 runs in a row;
`./demo/expect-errors.sh`: exit code 0). Every screen is the real console app running on the recording laptop; the
`sql` screen queries a real SQLite database file that the app creates (EF Core 10 + SQLite, embedded, no server).
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). **No VM, no tenant, no Azure resources.** | — |
| .NET SDK 10.0.1xx | `dotnet --version` (built and tested with 10.0.115) | free |
| NuGet access | first restore downloads `Microsoft.EntityFrameworkCore.Sqlite` 10.0.15 + xUnit | free |
| Windows Terminal | dark theme, font 18 pt or larger, ~150 columns (the SQL lines are long) | free |
| VS Code + C# Dev Kit | optional, for the split with `samples/requests.csv` | free |

## Setup (once, before recording)
```powershell
cd series\programming-languages\episodes\04-linq-functional-programming
dotnet test LinqFunctional.slnx -m:1          # expect Passed: 34 (restores and builds everything)
dotnet build src\Contoso.Portfolio.Cli -m:1
function prompt { '> ' }                        # short prompt: no user name or path on screen
$Host.UI.RawUI.WindowTitle = 'portfolio'
cls
```
Run each command below once as a rehearsal (JIT warm-up), then `cls` before each capture.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/report.jpg`** — *The report, from pure functions* (scene `report`)
   - `dotnet run --no-build --project src\Contoso.Portfolio.Cli -- report`
   - Frame: the totals block (`IT 4 requests 354,500 EUR`), the LeftJoin block ending with `Legal 0 0 EUR`,
     `Draft=2 Submitted=4 Approved=5 Rejected=1`, the top 3, and `method syntax == query syntax: True`.

2. **`screens/import.jpg`** — *Four good lines, four readable errors* (scene `import`)
   - `dotnet run --no-build --project src\Contoso.Portfolio.Cli -- import samples\requests.csv`
   - Frame: `requests.csv: 4 accepted, 4 rejected`, four `ok` lines, the four `line N:` errors.
   - Optional: VS Code on the left with `samples/requests.csv` open (lines 4, 6, 7, 8 are the bad ones).

3. **`screens/deferred.jpg`** — *Proof: the analyzer and the counter* (scene `deferredrun`)
   - `dotnet build demo\Analyzers -m:1 --no-incremental -v q` → two `error CA1851` lines (paths are relative
     enough; if the absolute path shows a user name, run from a folder under `C:\lab` or crop).
   - `dotnet run --no-build --project src\Contoso.Portfolio.Cli -- deferred` → `source read 3 times`,
     `source read 1 time`, `big.Count() = 5`, `big.Count() = 1`.
   - (Git Bash/WSL alternative: `./demo/expect-errors.sh` prints both parts plus the `ok` checks.)

4. **`screens/sql.jpg`** — *What the database actually received* (scene `sql`)
   - `dotnet run --no-build --project src\Contoso.Portfolio.Cli -- sql` (recreates `portfolio.db` each run).
   - Frame: the IQueryable block (`WHERE ef_compare("r"."Budget", @threshold) >= 0`, `5 results, 5 rows read`),
     the IEnumerable block (no `WHERE`, `5 results, 12 rows read`) and the `LEFT JOIN` block with Legal 0.
     The CountBy / C# method errors further down are for the `translate` code slide; capture a second frame of them
     for B-roll if useful.

The `gotcha`, `iqueryable` and `translate` scenes are code slides; their proof is screens 3 and 4 and the tests
`Gotcha_the_lambda_sees_the_variable_at_enumeration_time`, `Gotcha_IEnumerable_parameter_reads_the_whole_table_silently`,
`Gotcha_CountBy_compiles_on_a_DbSet_but_EF_Core_10_cannot_translate_it`.

## Masking
- Short prompt and window title as above. All data is fictional (`PR-2026-01xx`, Contoso departments). Nothing to blur.
- Compiler error lines include the full project path: record from a neutral folder (e.g. `C:\lab\mg-lab\...`) or crop.

## Tear-down
- `Remove-Item portfolio.db` (also git-ignored).
- `Get-ChildItem -Recurse -Directory -Include bin,obj | Remove-Item -Recurse -Force`
- Nothing was created outside the folder.
