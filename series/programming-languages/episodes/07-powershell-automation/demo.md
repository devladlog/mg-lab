# Demo shot list — DEVLADLOG Code #7 PowerShell automation, the safe way

Everything was built and tested in the container (`build.ps1`: analyzer 0 findings, **Pester 29 passed**). Every screen
is real PowerShell 7 running the real module and the real PSScriptAnalyzer on the recording laptop; the Pester tests use
a temporary folder, the screens use `.\out`. Reference output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). **No VM, no tenant, no Azure resources, no sign-in.** | — |
| PowerShell 7.6 | `winget install --id Microsoft.PowerShell --source winget` (Learn: install on Windows); check `$PSVersionTable.PSVersion` is 7.6.x. The video runs in `pwsh`, not in Windows PowerShell 5.1. | free |
| Pester and PSScriptAnalyzer | `Install-PSResource -Name Pester, PSScriptAnalyzer -Scope CurrentUser -TrustRepository` (Windows PowerShell 5.1 has Pester 3.4: `Get-Module Pester -ListAvailable` in `pwsh` must show 5.x or later; tested with 6.2.0 and 1.25.0) | free |
| Windows Terminal | dark theme, font 18 pt or larger, ~150 columns | free |
| VS Code + PowerShell extension | optional B-roll: `Export-ContosoApprovalPack.ps1` and the Pester test file | free |

## Setup (once, before recording)
```powershell
cd C:\lab\mg-lab\series\programming-languages\episodes\07-powershell-automation   # neutral path: no user name on screen
pwsh -NoProfile -File .\build.ps1                       # rehearsal: expect "findings: 0" and "Tests Passed: 29"
pwsh -NoProfile -File .\demo\run-demo.ps1               # rehearsal of screens 1-3
function prompt { '> ' }
$Host.UI.RawUI.WindowTitle = 'powershell-automation'
Remove-Item .\out -Recurse -Force -ErrorAction SilentlyContinue
cls
```
Open the terminal as `pwsh -NoProfile` so no profile output or custom prompt shows. Run each screen once as a rehearsal,
then `cls` before the capture.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/analyzer.jpg`** — *Gate one: PSScriptAnalyzer* (scene `analyzer`)
   - `Invoke-ScriptAnalyzer .\demo\bad-script.ps1 -Settings .\PSScriptAnalyzerSettings.psd1 | Sort-Object Line | Format-Table RuleName, Severity, Line -AutoSize`
   - Frame: 13 rows; the one `Error` (`PSAvoidUsingConvertToSecureStringWithPlainText`, line 7), `PSAvoidUsingWriteHost`,
     `PSAvoidUsingInvokeExpression`, `PSAvoidUsingEmptyCatchBlock`, `PSAvoidUsingCmdletAliases`, `PSUseApprovedVerbs`.
   - Then: `(Invoke-ScriptAnalyzer .\src -Recurse -Settings .\PSScriptAnalyzerSettings.psd1).Count` -> `0`.

2. **`screens/pipeline.jpg`** — *Objects in, errors on the side* (scene `pipeline`)
   - `Import-Module .\src\ContosoRequests\ContosoRequests.psd1 -Force`
   - `$requests = Import-ContosoRequest .\samples\requests.csv -ErrorVariable rejected -ErrorAction SilentlyContinue`
   - `"$($requests.Count) valid, $($rejected.Count) rejected"` -> `9 valid, 4 rejected`
   - `$requests | Format-Table Code, Title, Department, Budget, Priority`
   - `$rejected | ForEach-Object { $_.FullyQualifiedErrorId.Split(',')[0] + '  ' + $_.ErrorDetails.Message }`
   - Frame: the table (`PR-2026-0303 ... 50000.00 High`, `PR-2026-0304 ... Board`) and the four error lines (row 9, 10, 11, 13).

3. **`screens/whatif.jpg`** — *What if, then for real* (scene `whatif`, also a Short)
   - `$routes = $requests | Get-ContosoApprovalRoute -ApproverPath .\samples\approvers.json -ErrorVariable unrouted -ErrorAction SilentlyContinue`
   - `$routes | Export-ContosoApprovalPack -Destination .\out -WhatIf` -> eight `What if: Performing the operation "Write approval pack" on target ".\out\IT\PR-2026-0301.json".`
   - `Test-Path .\out` -> `False`
   - `$routes | Export-ContosoApprovalPack -Destination .\out -PassThru | Format-Table Code, Priority, Approvers`
   - `Get-Content .\out\IT\PR-2026-0304.json` -> the Board request with three approvers
   - `$routes | Export-ContosoApprovalPack -Destination .\out` -> eight `ContosoPack.AlreadyExists` errors
   - For the Short use only the `-WhatIf` lines and the first table. The "no route" error for Legal is in `$unrouted`:
     `$unrouted[0].Exception.Message`.

4. **`screens/gotchas.jpg`** — *Three gotchas, running* (scene `gotchas`)
   - `cls; pwsh -NoProfile -File .\demo\gotchas.ps1`
   - Frame: `caught=False requests=9` / `caught=True ... requests=0`, `wrong : 0 | 1 | PR-1 | PR-2`, and the three JSON lines
     (default shows `System.Collections.Specialized.OrderedDictionary` twice, the truncation warning, `-Depth 5` shows approvers).

5. **`screens/build.jpg`** — *One command, two gates* (scene `build`)
   - `cls; pwsh -NoProfile -File .\build.ps1`
   - Frame: `findings: 0`, the two test files (2 and 27 tests), `Tests Passed: 29, Failed: 0, ...`. Pester prints full file
     paths: that is why the working folder is `C:\lab\mg-lab`.
   - Optional second take for the closing line "the script exits with code one": add a `Write-Host 'x'` to any file under
     `src\` (or change `-ge 50000` to `-gt 50000` in `Get-ContosoPriority.ps1`), run `build.ps1`, show `$LASTEXITCODE` = 1,
     then revert the change. Do not leave the edit in the repo.

The code scenes (`legacy`, `import`, `route`, `export`, `trycatch`, `output`, `tests`) are slides with excerpts from the
repo. Their proof is the screens above and the tests in `tests\ContosoRequests.Tests.ps1`.

## Masking
- Short prompt, neutral folder and window title as above. All data is fictional (`PR-2026-03xx`, Alex/Sam/Jordan/Riley/Taylor
  Demo as plain strings in `approvers.json`, not accounts). Nothing to blur.
- Pester and `Resolve-Path` print absolute paths: keep the repo under `C:\lab\mg-lab`.

## Tear-down
- `Remove-Item .\out -Recurse -Force -ErrorAction SilentlyContinue` (the folder is in `.gitignore`).
- `Remove-Module ContosoRequests`; `git status` should show no change outside `out\`.
- Nothing was created outside the folder; nothing to delete in any tenant. (Pester and PSScriptAnalyzer stay installed
  for the other PowerShell episodes.)
