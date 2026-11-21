# DEVLADLOG Code #7 — PowerShell automation, the safe way (PowerShell 7.6)

The Contoso project requests from episodes 1-6 now need an **approval pack** per request (a JSON file in a folder per
department). We build it the way a PowerShell script should be written today, and compare it with the legacy script
everybody copies between servers:

- **Gate one: PSScriptAnalyzer.** `demo/bad-script.ps1` (plain-text password, `Write-Host`, `Invoke-Expression`, empty
  `catch`, aliases, an unapproved verb) gets **13 findings, 1 of them an Error**. The module gets **0**.
- **A module, not a script**: `ContosoRequests` with a manifest, three public functions and private helpers.
- **Advanced functions**: `[CmdletBinding()]`, validated parameters with a custom `ErrorMessage`, pipeline input by
  value and by property name (`Get-ChildItem x.csv | Import-ContosoRequest`), `[OutputType]`.
- **Objects, not text**: `Contoso.Request` (decimal budget, real `datetime`, priority) and `Contoso.ApprovalRoute`;
  formatting only at the end of the pipeline.
- **Error handling with intent**: a bad CSV row is a *non-terminating* error written with `$PSCmdlet.WriteError` (stable
  error id, the row as target, row number in `ErrorDetails`), so the rest of the file is still processed. A broken
  approvers file stops the whole command. `-ErrorVariable` collects the rejected rows.
- **`-WhatIf` / `-Confirm`** with `SupportsShouldProcess`, no overwrite without `-Force`, so the export is safe to re-run.
- **Gate two: Pester** (29 tests: 27 on the module, 2 that run the analyzer) and `build.ps1`, which exits with code 1
  if either gate fails.
- **Three real gotchas** (`demo/gotchas.ps1`): `try/catch` and non-terminating errors, accidental pipeline output from
  `ArrayList.Add`, and `ConvertTo-Json` depth.

| Path | What it is |
|---|---|
| [`src/ContosoRequests/ContosoRequests.psd1`](src/ContosoRequests/ContosoRequests.psd1) / [`.psm1`](src/ContosoRequests/ContosoRequests.psm1) | Manifest (requires PowerShell 7.6, exports exactly 3 functions) and a loader that dot-sources `Private/` and `Public/` |
| [`src/ContosoRequests/Public/Import-ContosoRequest.ps1`](src/ContosoRequests/Public/Import-ContosoRequest.ps1) | CSV to `Contoso.Request`; bad rows become non-terminating errors |
| [`src/ContosoRequests/Public/Get-ContosoApprovalRoute.ps1`](src/ContosoRequests/Public/Get-ContosoApprovalRoute.ps1) | Manager, then finance (High, Board), then the board (Board); unknown department is a per-request error |
| [`src/ContosoRequests/Public/Export-ContosoApprovalPack.ps1`](src/ContosoRequests/Public/Export-ContosoApprovalPack.ps1) | `<Destination>/<Department>/<Code>.json`; `-WhatIf`, `-Force`, `-PassThru`; `ConvertTo-Json -Depth 5`; UTF-8 without BOM |
| [`src/ContosoRequests/Private/`](src/ContosoRequests/Private) | `ConvertTo-ContosoRequest` (validation, never throws), `Get-ContosoProblem`, `Get-ContosoPriority` (>= 50,000 High, >= 250,000 Board, the series rule from episode 6) |
| [`samples/requests.csv`](samples/requests.csv) / [`samples/approvers.json`](samples/approvers.json) | 13 fictional rows (9 valid, 4 bad: `abc`, `-500`, `REQ-77`, `2026-13-01`, plus a `Legal` row with no approver and a lower-case `it`) and the approvers (same people as episode 5) |
| [`tests/ContosoRequests.Tests.ps1`](tests/ContosoRequests.Tests.ps1) | 27 Pester tests |
| [`tests/Analyzer.Tests.ps1`](tests/Analyzer.Tests.ps1) | 2 tests: the module is clean, the legacy script is not (13 findings) |
| [`build.ps1`](build.ps1) / [`PSScriptAnalyzerSettings.psd1`](PSScriptAnalyzerSettings.psd1) | Both gates in one command; Warning and Error fail the build |
| [`demo/bad-script.ps1`](demo/bad-script.ps1) | The legacy script (a "before", it is not meant to be run) |
| [`demo/run-demo.ps1`](demo/run-demo.ps1) / [`demo/gotchas.ps1`](demo/gotchas.ps1) | The screens of the video as scripts, for rehearsal |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of `build.ps1`, `run-demo.ps1` and `gotchas.ps1` |

## Build, test, run

```powershell
# once: PowerShell 7.6, then the two modules (Windows PowerShell 5.1 ships Pester 3.4, which is too old)
Install-PSResource -Name Pester, PSScriptAnalyzer -Scope CurrentUser -TrustRepository
pwsh -NoProfile -File ./build.ps1                       # analyzer: 0 findings, Pester: Tests Passed: 29, Failed: 0 (exit code 0)
Invoke-Pester ./tests -Output Detailed                  # just the tests
pwsh -NoProfile -File ./demo/run-demo.ps1               # the screens, end to end
pwsh -NoProfile -File ./demo/gotchas.ps1                # the three gotchas
```

The manual version, as in the video:

```powershell
Import-Module ./src/ContosoRequests/ContosoRequests.psd1 -Force
$requests = Import-ContosoRequest ./samples/requests.csv -ErrorVariable rejected -ErrorAction SilentlyContinue
$requests | Get-ContosoApprovalRoute -ApproverPath ./samples/approvers.json -ErrorAction SilentlyContinue |
    Export-ContosoApprovalPack -Destination ./out -WhatIf          # nothing is written
```

Tested here with PowerShell 7.6.0, Pester 6.2.0 and PSScriptAnalyzer 1.25.0 on Ubuntu 24.04: **29 tests passed**, repeated
runs green; to check that the tests really test, we broke the code on purpose (`>=` to `>` at 50,000; `-Depth 5`
removed; a `Write-Host` added) and the build failed each time (exit code 1 confirmed for the `>=` and `Write-Host` cases). No cloud resources and no tenant are
needed: the screens are recorded on the Windows laptop. **Not tested here:** Windows (path separators, the Windows
file system being case-insensitive) and Windows PowerShell 5.1 (the module needs 7.6).

## What we learned / gotchas

- **`try/catch` does not catch non-terminating errors.** Our `Import-ContosoRequest` writes one error per bad row and
  keeps going, so `try { ... } catch { }` never fires. With `-ErrorAction Stop` it does, at the first bad row, and the
  seven good rows before it are discarded because the assignment never completes (Learn: *Everything you wanted to know
  about exceptions*; `WriteError` lets the command continue, `ThrowTerminatingError` stops it).
- **A caught exception inside a helper leaks into the caller's `-ErrorVariable`.** Our first version threw from a
  private function and caught it in the public one: `-ErrorVariable rejected` held **24 entries for 4 bad rows**. The
  private function now returns a problem object and never throws; the count is exactly 4. (Observed here; not
  something Learn spells out.)
- **`ArrayList.Add` returns the index**, which goes into the function's output: `0 | 1 | PR-1 | PR-2`. Use `$null = ...`.
- **`ConvertTo-Json -Depth` defaults to 2** (Learn: default value 2). Since PowerShell 7.1 it warns when the depth is
  exceeded, but the output is already wrong: the approvers became the text `System.Collections.Specialized.OrderedDictionary`.
  The module passes `-Depth 5` and a test reads all three approvers of a Board request back.
- **`-WhatIf` output goes straight to the host.** It can't be captured with `*>&1` or `6>&1`, so the test that checks
  the eight "What if:" lines runs a child `pwsh` and reads its stdout.
- **Casing of department names.** The CSV has `it`; the approvers file has `IT`. On Windows both would land in the same
  folder, on Linux in two. The route now carries the department spelling from the approvers file, and a test pins `IT`.
- **PSScriptAnalyzer flagged our own helper**: `New-ContosoProblem` triggered `PSUseShouldProcessForStateChangingFunctions`
  (a `New-` function should support `-WhatIf`) although it only builds an in-memory object. Renamed to `Get-ContosoProblem`.
- **`Format-Table` needs a console width.** Without a terminal (for example a CI log), `Format-Table | Out-String` came out
  blank here; use `Out-String -Width 150` or run under a pty. The expected output was captured under a 150-column pty.
- **Aliases are not portable**: on Linux `Sort` is not defined (it would shadow `/usr/bin/sort`), and the same script
  that works on a Windows laptop fails on a Linux agent. The analyzer rule `PSAvoidUsingCmdletAliases` exists for this.
- **PowerShell versions**: PowerShell 7.4 LTS reached end of support on 10 Nov 2026; 7.6 LTS is supported until
  14 Nov 2028 (Learn: *PowerShell Support Lifecycle*). The manifest requires 7.6 because that is the version we tested.
- **Pester**: Windows PowerShell 5.1 ships Pester 3.4.0 (Learn: *about_Windows_PowerShell_5.1*); the tests use the
  Pester 5+ syntax (`BeforeAll`, `-ForEach`, `Should -Be`) and declare `#Requires -Modules` Pester 5.0.0.
- **Encoding**: `Set-Content` defaults to `utf8NoBOM` in PowerShell 7 but to the ANSI code page in Windows PowerShell
  (Learn: *about_Character_Encoding*). The module sets `-Encoding utf8NoBOM` explicitly and a test checks the first byte.

## References
- [about_Functions_CmdletBindingAttribute (`SupportsShouldProcess`, `ConfirmImpact`)](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_functions_cmdletbindingattribute)
- [Everything you wanted to know about ShouldProcess](https://learn.microsoft.com/powershell/scripting/learn/deep-dives/everything-about-shouldprocess)
- [Everything you wanted to know about exceptions (terminating vs non-terminating)](https://learn.microsoft.com/powershell/scripting/learn/deep-dives/everything-about-exceptions) and [about_Error_Handling](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_error_handling)
- [`ConvertTo-Json` (`-Depth`, default 2, warning since 7.1)](https://learn.microsoft.com/powershell/module/microsoft.powershell.utility/convertto-json)
- [Using PSScriptAnalyzer (settings files, presets)](https://learn.microsoft.com/powershell/utility-modules/psscriptanalyzer/using-scriptanalyzer) and [`Invoke-ScriptAnalyzer`](https://learn.microsoft.com/powershell/module/psscriptanalyzer/invoke-scriptanalyzer)
- [PowerShell Support Lifecycle](https://learn.microsoft.com/powershell/scripting/install/powershell-support-lifecycle) and [Install PowerShell 7 on Windows](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows)
- [about_Windows_PowerShell_5.1 (ships Pester 3.4.0)](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_windows_powershell_5.1) and [about_Character_Encoding](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_character_encoding)
- [`Install-PSResource`](https://learn.microsoft.com/powershell/module/microsoft.powershell.psresourceget/install-psresource)
- Blog: [PowerShell Automation — Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-17-powershell-automation-complete-guide-2025/)
