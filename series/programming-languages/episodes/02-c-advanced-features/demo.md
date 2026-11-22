# Demo shot list — DEVLADLOG Code #2 Advanced C# (C# 14 on .NET 10)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none: the screens show the real C# 14 compiler, the demo app and VS Code IntelliSense on this project |
| Licences / cost | none (VS Code + C# Dev Kit; no Visual Studio licence needed) |
| Recording machine | The Windows lab laptop: .NET SDK 10.0.1xx, VS Code + C# Dev Kit, a bash terminal (Git Bash or WSL) for `./demo/expect-errors.sh`, opened under a neutral path |

Everything here was built and tested in the container (`dotnet test`: **53 passed**; `./demo/expect-errors.sh`:
all checks ok). **No tenant, no cloud resources, no licences needed**: all three screens are local captures.
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET SDK 10.0.1xx | `dotnet --version` (tested with 10.0.115) | free |
| VS Code + C# Dev Kit | for the IntelliSense screen; dark theme, font ≥ 18 | free |
| Terminal | dark theme, font ≥ 18 pt, ~140 columns (the compiler messages are long) | free |
| Masking | terminal prompt and absolute paths only (`expect-errors.sh` already strips the repo path). `export PS1='$ '` | — |

## Setup
```bash
cd series/programming-languages/episodes/02-c-advanced-features
dotnet test AdvancedCSharp.slnx -m:1        # expect Passed: 53 (also warms up the build)
export PS1='$ '
clear
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/editor-extension.jpg`** — *Extension properties in IntelliSense* (scene `editor`)
   - `code .` → `src/Contoso.Requests.Demo/Program.cs`. Wait for the C# Dev Kit to load the solution
     (`AdvancedCSharp.slnx`).
   - Hover `TotalBudget` inside `{requests.TotalBudget}` on line 28 (the second one on the line; the first is string
     text), then `HighPriority` on line 29, then `clock.Today` on line 30. Each tooltip shows the extension property
     (signature with `{ get; }`); TotalBudget and Today show their doc comments. No typing: the recording is done with
     clicks and hovers only, so the completion list (which needs a key) is not part of the take.
   - Recording kit: `record.json` opens this exactly (`Open-VsCodeScene.ps1`). Write down the tooltip wording.
   - Mask the window title / explorer root if it shows a user name.

2. **`screens/demo-run.jpg`** — *The walk-through* (scene `run`)
   - `dotnet run --project src/Contoso.Requests.Demo`
   - Frame must show: the routing table (TeamLead / Finance / Board), `requests.TotalBudget = 393,000 EUR`, the
     workflow lines (`REFUSED You can't approve your own request.`, `approvals=[Finance]`,
     `Approved by alex.demo@contoso.com approvals=[Finance, Board]`) and `parsed 3 codes, allocated 0 bytes`.
     If it doesn't fit, capture from `== Extension members` down.

3. **`screens/gotchas.jpg`** — *Only warnings, unless you say so* (scene `gotchas`)
   - `./demo/expect-errors.sh`
   - Frame must show the CS9264 / CS9258 / CS8509 lines, the six `ok` checks and `C# 13: [1, 2, 3].Average() = 2`.
   - Optional split for the narration "the build just succeeds":
     `dotnet build demo/Gotchas -p:TreatWarningsAsErrors=false -v q` → `Build succeeded` with warnings CS8509,
     CS9258, CS9264.

No screen needs a tenant. The `gotcha` scene (C# 13 vs C# 14 binding) is a code slide; its proof is the
`demo/CSharp13` run plus the unit test `Gotcha_a_span_extension_now_beats_LINQ_on_an_array`.

## Tear-down
```bash
find . -type d \( -name bin -o -name obj \) -prune -exec rm -rf {} +
```
Nothing was created outside the folder.
