# Demo shot list — DEVLADLOG Code #6 Clean code principles, proven

Everything was built and tested in the container (`dotnet test`: **18 passed**, 5 runs in a row;
`./demo/expect-errors.sh`: exit code 0). Every screen is the real compiler and the real console app running on the
recording laptop; the comparison runs the actual legacy class and the actual clean class on the same file. Reference
output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). **No VM, no tenant, no Azure resources.** | — |
| .NET SDK 10.0.1xx | `dotnet --version` (built and tested with 10.0.115). The analyzers (CA*, IDE*) ship with the SDK. | free |
| NuGet access | first restore downloads xUnit + Microsoft.NET.Test.Sdk (tests only) | free |
| Windows Terminal + PowerShell 7 | dark theme, font 18 pt or larger, ~150 columns (error lines and the comparison table are long) | free |
| VS Code + C# Dev Kit | optional B-roll: `RequestProcessor2.cs` next to `RequestProcessor.cs`, Test Explorer with 18 green tests | free |

## Setup (once, before recording)
```powershell
cd series\programming-languages\episodes\06-clean-code-principles
dotnet test CleanCode.slnx -m:1                 # expect Passed: 18 (restores and builds everything)
dotnet build src\Contoso.Requests.Cli -m:1
function prompt { '> ' }                        # short prompt: no user name or path on screen
$Host.UI.RawUI.WindowTitle = 'clean-code'
cls
```
Run each command once as a rehearsal, then `cls` before each capture. Don't run the `golden` command during
recording: it would overwrite the approved master (only ever generate it from the legacy code).

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/gates.jpg`** — *The legacy code against the gates* (scene `gatesrun`)
   - `dotnet build src\Contoso.Requests.Legacy -m:1 --no-incremental -v q -p:EnforceCleanCode=true`
   - Frame: `error CA1502: 'Process' has a cyclomatic complexity of '19'. Rewrite or refactor the code to decrease its
     complexity below '11'.`, a block of `IDE0011: Add braces to 'if' statement.`, `IDE0059: Unnecessary assignment of
     a value to 'r'`, `CA1031: Modify 'Process' to catch a more specific allowed exception type...` and `17 Error(s)`.
   - Then, same window: `dotnet build src\Contoso.Requests.Clean -m:1 --no-incremental -v q` → `0 Error(s)`.
   - Error lines contain the full path of the file: record from a neutral folder (e.g. `C:\lab\mg-lab\...`) so no
     user name shows, or crop the path.

2. **`screens/compare.jpg`** — *38 identical, 2 different, on purpose* (scene `compare`)
   - `dotnet run --no-build --project src\Contoso.Requests.Cli -- compare samples\requests.csv`
   - Frame: `clean code rounding: ToEven`, the 20-line table with `same`, the two `07 ... DIFF` lines (N vs H) and
     `20 lines x 2 modes: 38 identical, 2 different`.
   - Optional split: VS Code with `golden\legacy-output.approved.txt` on the left.

3. **`screens/rounding.jpg`** — *The master catches it* (scene `roundingrun`)
   - `dotnet run --no-build --project src\Contoso.Requests.Cli -- compare samples\requests.csv --rounding AwayFromZero`
   - Frame: `clean code rounding: AwayFromZero`, the `09 plain ... 12500   DIFF ... 12501` and `09 mail` lines,
     and `20 lines x 2 modes: 36 identical, 4 different`.

The code scenes (`legacy`, `gates`, `golden`, `processor`, `policy`, `flag`, `rounding`, `culture`) are slides with
excerpts from the repo. Their proof is the screens above and the tests
`Clean_code_matches_the_master_except_the_intentional_changes`,
`Gotcha_rounding_away_from_zero_changes_an_amount_people_already_approved`,
`The_master_pins_the_order_of_the_checks`, `Gotcha_the_catch_all_turned_a_null_line_into_a_normal_looking_error` and
`Gotcha_a_culture_bug_the_golden_master_could_not_see` (needs ICU culture data, which Windows 10/11 and the
container both have). Optional B-roll: `dotnet test CleanCode.slnx -m:1` → `Passed: 18`.

(Git Bash/WSL alternative for a rehearsal: `./demo/expect-errors.sh` runs all three screens with ok/FAIL checks.)

## Masking
- Short prompt and window title as above. All data is fictional (`PR-2026-02xx`, departments IT/OPS/MKT/HR/LEGAL,
  logins like `alex.demo`, which are only strings in the code, not accounts). Nothing to blur.
- Only the gates screen shows file paths (compiler errors): neutral folder or crop.

## Tear-down
- `Get-ChildItem -Recurse -Directory -Include bin,obj | Remove-Item -Recurse -Force`
- `git status` should show no change to `golden\legacy-output.approved.txt`. Nothing was created outside the folder.
