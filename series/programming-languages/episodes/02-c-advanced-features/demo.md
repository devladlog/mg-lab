# Demo shot list — DEVLADLOG Code #2 Advanced C# (C# 14 on .NET 10)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none: the screens show the real C# 14 compiler, the demo app and VS Code IntelliSense on this project |
| Licences / cost | none (VS Code + the C# extension; C# Dev Kit is not needed and was off in the recorded window) |
| Recording machine | The Windows lab laptop: .NET SDK 10.0.303, VS Code 1.147 with the C# extension 2.160.4 (C# Dev Kit off for the recorded window), PowerShell 7.6.10 starting Git Bash for `./demo/expect-errors.sh`, opened under the neutral path `C:\lab\pl02` |

Everything here was built and tested in the container (`dotnet test`: **53 passed**; `./demo/expect-errors.sh`:
all checks ok). **No tenant, no cloud resources, no licences needed**: all three screens are local captures.
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET 10 SDK | `dotnet --version` (container tests: 10.0.115; takes recorded with 10.0.303) | free |
| VS Code + C# extension | for the editor screen (hover tooltips); dark theme, font ≥ 18. C# Dev Kit is not needed | free |
| Terminal | dark theme, font ≥ 18 pt, ~140 columns (the compiler messages are long) | free |
| Masking | terminal prompt and absolute paths only. `export PS1='$ '`. `expect-errors.sh` strips the repo path under bash; on Windows the compiler prints `C:\lab\pl02\demo\Gotchas\...` and it stays (neutral lab folder, nothing personal). VS Code: the activity bar shows the account picture, so the `editor` scene is cropped in script.yaml | — |

## Setup
```bash
cd series/programming-languages/episodes/02-c-advanced-features
dotnet test AdvancedCSharp.slnx -m:1        # expect Passed: 53 (also warms up the build)
export PS1='$ '
clear
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/editor-extension.jpg`** — *Extension properties in the editor* (scene `editor`)
   - `code .` → `src/Contoso.Requests.Demo/Program.cs`. Wait for the C# extension to load the solution
     (`AdvancedCSharp.slnx`; the status bar shows `{} C#`). The take runs with the C# extension only, C# Dev Kit off.
   - Hover `TotalBudget` inside `{requests.TotalBudget}` on line 28 (the second one on the line; the first is string
     text), then `HighPriority` on line 29, then `clock.Today` on line 30. Each tooltip shows the extension property
     (signature with `{ get; }`); TotalBudget and Today show their doc comments. No typing: the recording is done with
     clicks and hovers only, so the completion list (which needs a key) is not part of the take.
   - Recording kit: `record.json` opens this exactly (`Open-VsCodeScene.ps1`) and moves the pointer by script.
   - Tooltip wording in the take (C# extension 2.160.4), each tooltip above its line:
     - `Euros RequestExtensions.extension(IEnumerable<ProjectRequest>).TotalBudget { get; }` and the doc comment
       `requests.TotalBudget, a property on a type we don't own.` (3.7 s to 9.0 s of the take)
     - `IEnumerable<ProjectRequest> RequestExtensions.extension(IEnumerable<ProjectRequest>).HighPriority { get; }` and
       the note `'HighPriority' is not null here.`, no doc comment (9.0 s to 13.3 s)
     - `DateOnly TimeProviderExtensions.extension(TimeProvider).Today { get; }` and
       `time.Today: an extension property on a framework type.` (13.3 s to 18.0 s)
   - Mask: window title (`Program.cs - pl02 - VS Code`) and Explorer root (`pl02`) show no user name. The activity bar
     shows the round account picture: `crop: [60, 44, 1844, 980]` in script.yaml removes title bar and activity bar.

2. **`screens/demo-run.jpg`** — *The walk-through* (scene `run`)
   - `dotnet run --project src/Contoso.Requests.Demo`
   - Frame must show: the routing table (TeamLead / Finance / Board), `requests.TotalBudget = 393,000 EUR`, the
     workflow lines (`REFUSED You can't approve your own request.`, `approvals=[Finance]`,
     `Approved by alex.demo@contoso.com approvals=[Finance, Board]`) and `parsed 3 codes, allocated 0 bytes`.
     If it doesn't fit, capture from `== Extension members` down.

3. **`screens/gotchas.jpg`** — *Only warnings, unless you say so* (scene `gotchas`)
   - `./demo/expect-errors.sh`
   - Frame must show the CS9264 / CS9258 / CS8509 lines, the six `ok` checks and `C# 13: [1, 2, 3].Average() = 2`.
   - In the take the typed line is `& 'C:\Program Files\Git\bin\bash.exe' ./demo/expect-errors.sh` (PowerShell starts
     Git Bash). The four error lines start with `C:\lab\pl02\demo\Gotchas\` and each wraps onto a second row, where
     the script's 200 character limit cuts it mid word. The optional split below was not recorded.
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
