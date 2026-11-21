# Demo shot list — DEVLADLOG .NET #10 .NET 8 and 9 Features

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / containers | none (the shared Hyper-V lab is not used) |
| Azure | **none**: no resource group, no cost (cost: EUR 0) |
| Lab tenant / licences | none |
| Recording machine | The Windows lab laptop (Windows Terminal, PowerShell 7, a browser). Software: **.NET SDK 10.0.1xx**, the **.NET 8 runtime** (`dotnet --list-runtimes` must show `Microsoft.NETCore.App 8.0.x`), and optionally the .NET 9 runtime. Git |
| Clone | `git clone https://github.com/devladlog/mg-lab` then `cd mg-lab\series\net\episodes\10-net-8-9-features` |

Every screen shows the real tour app, the real compiler output and the real test run; nothing is mocked.

Built and verified in the build container (Linux, SDK 10.0.115, .NET 8.0.34 and 10.0.15 runtimes): `dotnet test -c Release`
**53 passed** (18 on net8.0, 35 on net10.0); Debug: 52 passed, 1 skipped (the allocation test). The tour output of both
runtimes and the compiler errors are saved in `deploy/`. **Not run on Windows.** **net9.0 was only compile-checked**
(`-p:IncludeNet9=true`); no .NET 9 runtime was available, so nothing was run on .NET 9 and the video claims nothing about it.
The GUID and the exact runtime build numbers on screen will differ from `deploy/`.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| `dotnet --version` is 10.0.1xx | `global.json` pins the SDK with roll-forward and selects the Microsoft.Testing.Platform runner | free |
| .NET 8 runtime installed | without it the net8.0 tour and test run fail with "You must install or update .NET" (the lab laptop has only .NET 10 as of 21 Nov 2026; .NET 8 support ended on 10 Nov 2026, so say so on screen and install the runtime only for this recording) | free |
| Terminal font 18-20 pt, dark theme | | — |
| Masking | the prompt shows the Windows user name: use `function prompt { "PS> " }`. No tenant names or URLs besides public Learn | — |

## Setup (before recording, not on camera)
```powershell
cd series\net\episodes\10-net-8-9-features
dotnet --list-runtimes                        # 8.0.x and 10.0.x present
dotnet test -c Release                        # expect: 53 succeeded, 0 failed
function prompt { "PS> " }
```

## Screens (match `screen` scenes in script.yaml)

### 1. `lifecycle` — "The dates" (browser, public)
Open `https://learn.microsoft.com/lifecycle/products/microsoft-net-and-net-core`, scroll to the table. Point at .NET 10 (LTS),
.NET 9 and .NET 8. **Re-read the dates on the day**: when built they were 11/11/2026 (.NET 8 and 9) and 11/15/2028 (.NET 10);
the narration quotes them. No sign-in.

### 2. `tour8` — "Run it on .NET 8" (terminal)
```powershell
dotnet run --project src\ProjectRequests.Features.Tour -f net8.0
```
Shows `compiled : net8.0`, the C# 12 section, and the .NET 9 section reporting it is not compiled in. Reference: `deploy\tour-net8.0.output.txt`.

### 3. `tour10` — "Run it on .NET 10" (terminal)
```powershell
dotnet run --project src\ProjectRequests.Features.Tour -f net10.0
```
Full output including `System.Threading.Lock : ... held in lock(Lock)=True, in lock(object)=False` and `Task.WhenEach : medium -> fast -> slow`.
Reference: `deploy\tour-net10.0.output.txt`.

### 4. `errors` — "Too early" (terminal)
```powershell
type deploy\net8-compile-errors.txt
```
Point at CS9202 (x2), CS1061, CS0117, CS0234. Optional live: scratch console project with `<TargetFramework>net8.0</TargetFramework>`
and one snippet from the file, then `dotnet build`. (Outside the repo folder; delete it afterwards.)

### 5. `tests` — "One test run, two runtimes" (terminal)
```powershell
dotnet test -c Release
```
One test app per target: net8.0 total 18, net10.0 total 35, 53 succeeded in total. About 20 s on the container.

## Gotcha and tip scenes (no screen)
All bullets are covered by tests or saved output; see the README "What we learned". The params allocation figures (0 bytes Release,
72 B per call Debug) were measured in the container: check them on the laptop before the narrator quotes them.

## Tear-down
```powershell
Get-ChildItem -Recurse -Directory -Include bin,obj,TestResults | Remove-Item -Recurse -Force
```
No Azure resources, nothing else to delete. Remove any scratch console project from screen 4.
