# Demo shot list - DEVLADLOG Code #11 Modern language features (TypeScript, C# 14, Python 3.13, PowerShell 7.6)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. No tenant, no sign-in, no cloud resources, no licences, no cost. |
| Recording machine | The Windows lab laptop (host, not a VM). Everything runs locally in VS Code and a terminal. |
| Software on the laptop | VS Code (+ C# Dev Kit optional), Node.js 22.18 or later (22.x LTS), .NET SDK 10.0.1xx, Python 3.13, PowerShell 7.6 (7.4 or later works), Git. Pester (`Install-Module Pester` if `Get-Module -ListAvailable Pester` is empty or older than 5). |
| Network | Only for `npm install` (typescript, @types/node) and the first `dotnet test` (NuGet: xUnit). The demo scripts themselves need none. |

Everything was built and tested in the Linux container (see `README.md`: 60 tests, `demo/conformance.ps1` all `[ok]`).
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt). **Not yet run on Windows**: do the
"Windows check" below before recording and write down anything that differs.

## Prerequisites and setup
```powershell
cd <repo>\series\programming-languages\episodes\11-modern-language-features
node --version        # v22.18 or later
dotnet --version      # 10.0.1xx
python --version      # 3.13.x   (on Windows use the python.org / winget install, not the Microsoft Store stub)
pwsh --version        # 7.6.x
$env:PYTHON = 'python'   # conformance.ps1 and gotchas.ps1 use this launcher (they fall back to python, then python3)
npm install --no-audit --no-fund
dotnet test ModernFeatures.slnx -m:1     # warms the NuGet cache and the build, expect Passed: 16
dotnet run src/cs/digest.cs -- samples/requests.json | Out-Null   # warms the file-based app cache
```
Terminal: dark theme, font 18 pt or larger, about 120 columns (the AOT error line in the gotchas is long, so use
`Select-Object -First 1` as the script does, or let it wrap). Prompt shortened (`function prompt { '$ ' }`).
Masking: explorer root, window title, and the absolute path in the Python `DeprecationWarning` line (crop or clear
the terminal and rerun with `$env:PYTHONWARNINGS` unset from a short path). There is nothing else sensitive: all data
is fictional (`contoso.com`, `alex.demo`).

### Windows check (do once, before recording)
```powershell
npm test                                  # 11 pass (line endings are normalised in the golden-file tests)
pwsh -File demo\conformance.ps1           # 4 x [ok]
pwsh -File demo\gotchas.ps1               # the 3 sections
python -m pip install pytest ruff mypy ; python -m pytest -q     # 16 passed
Invoke-Pester -Path tests\ps              # 17 passed
```
If `conformance.ps1` fails for one language on Windows, the diff it prints shows the first differing lines. Most likely
causes: CRLF in `expected/digest.txt` (the repo has `.gitattributes` for LF, but a copy outside git may not), or a
non-invariant culture (all four use invariant formatting, so a mismatch is a real bug: report it).

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/node-ts.jpg`** - *No build step* (scene `ts-run`)
   - `code .`, open `src/ts/digest.ts`, scroll to the `Map.groupBy` block; integrated terminal below.
   - `node src/ts/main.ts samples/requests.json` - the full digest ("Contoso request digest" ... three batches).
   - `npx tsc -p tsconfig.json` - no output (exit 0). Optionally `$LASTEXITCODE` to show `0`.
   - Capture with both the code and the digest visible.
   - Recording kit (`record.json`, `Open-VsCodeScene.ps1`): the take is clicks only, so both commands are VS Code
     tasks (Terminal > Run Task...; the task terminal echoes each command) and the task terminal opens as a tab in
     a second editor group, on the right of the code, so `Map.groupBy` and the digest are visible together.

2. **`screens/csharp-file-app.jpg`** - *dotnet run digest.cs* (scene `cs-run`)
   - `dotnet --version`, then `dotnet run src/cs/digest.cs -- samples/requests.json`.
   - If the terminal shows build output, run it a second time (the host caches the build) and capture that one.
   - Visible: the whole digest. Optional extra capture: `code src/cs/digest.cs` showing the `#:project` and
     `#:property PublishAot=false` lines at the top.

3. **`screens/conformance.jpg`** - *Same input, same output* (scene `conformance`, Short)
   - `pwsh demo/conformance.ps1`
   - Frame: the Toolchain block, four `[ok]` lines (each "23 lines, identical to expected/digest.txt") and
     "All four languages print the same digest." Takes ~20-40 s the first time; record the run, trim the wait.

4. **`screens/gotchas.jpg`** - *Where it bites* (scene `gotchas`, Short)
   - `pwsh demo/gotchas.ps1`
   - Frame: section 1 (`ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX` and `TS1294`), section 2 (`Reflection-based serialization
     has been disabled`), section 3 (the `0.29 * 100` lines: 28, 28, 28, then PowerShell 29). If it does not fit,
     capture sections 1-2 and 3 separately and cut between them.

The code scenes (`ts-code`, `cs-code`, `cs-lib`, `py-code`, `ps-code`) are slides built from the real files; every excerpt
is verbatim from `src/`. The `tests` scene is a bullet slide; if you want proof on screen, run the four test commands
from `README.md` and show the counts (11, 16, 16, 17).

## Needs the tenant
Nothing. No screen uses a mock or stand-in: each one shows the real runtime (Node, the .NET host, Python, PowerShell)
running the real files of this folder.

## Tear-down
```powershell
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Include bin,obj,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache | Remove-Item -Recurse -Force
dotnet clean src/cs/digest.cs      # removes the file-based app cache for this file
```
Nothing was created outside the folder and the user-level caches (NuGet, npm).
