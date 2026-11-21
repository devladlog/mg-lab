# DEVLADLOG Dev Tools #12 - Visual Studio tips and tricks: the ones that live in the repository

The orders API from [episode 9](../09-debugging-techniques/) (healthy code, no bug patches) gets **the files Visual Studio reads**, so the
next person who clones it gets the same IDE setup: **what to install** (`.vsconfig`), **what to open** (solution filters), **what to type**
(code snippets), **how tests run** (`.runsettings`) and **how the app starts** (launch profiles, Hot Reload). Everything that can be proved
without Visual Studio is proved here with the `dotnet` CLI and real processes; what only exists inside the IDE is recorded on Windows
(see [demo.md](demo.md)). Debugging, profiling, code quality and packages are in episodes 6 to 11 and are not repeated.

```
 .vsconfig                       ──► Visual Studio Installer / "missing components" bar when the solution opens
 OrdersApp.slnx                  ──► the whole solution (dotnet build with no name takes this one)
   OrdersApp.Api.slnf            ──► load and build only the API
   OrdersApp.Tests.slnf          ──► the tests (+ the project they reference, pulled in by MSBuild)
 .runsettings  ◄── <RunSettingsFilePath> in Directory.Build.props ──  Test Explorer, dotnet test, pipeline
 snippets/ordtest.snippet        ──► Code Snippets Manager (Ctrl+K, Ctrl+B): type ordtest, Tab, Tab
 snippets/ordscope.snippet       ──► Surround With: wraps the selection in a logging scope
 Smoke.playlist                  ──► Test Explorer playlist = the tests with [Trait("Category","Smoke")]
 Properties/launchSettings.json  ──► the toolbar's profile drop-down; env vars; Hot Reload on/off per profile
 tools/vs_files.py check         ──► the pipeline guard for all of the above;  expand = what a snippet inserts
```

| Path | What it is |
|---|---|
| [`src/orders-app/.vsconfig`](src/orders-app/.vsconfig) | `"version": "1.0"` and five IDs: the **ASP.NET and web development** workload, .NET SDK, Git, .NET profiling tools, IntelliCode. Next to the solution on purpose (Learn: Visual Studio prompts for missing components when it is in the solution root) |
| [`src/orders-app/OrdersApp.Api.slnf`](src/orders-app/OrdersApp.Api.slnf), [`OrdersApp.Tests.slnf`](src/orders-app/OrdersApp.Tests.slnf) | Solution filters over [`OrdersApp.slnx`](src/orders-app/OrdersApp.slnx) (paths with doubled backslashes, as Visual Studio writes them) |
| [`src/orders-app/.runsettings`](src/orders-app/.runsettings) | `MaxCpuCount` 1, `TestSessionTimeout` 300000, `TreatNoTestsAsError` true, environment variable `CONTOSO_REGION=lab-west` |
| [`src/orders-app/Directory.Build.props`](src/orders-app/Directory.Build.props) | Episode 5's lock-file setting plus `RunSettingsFilePath` pointing at `.runsettings` |
| [`src/orders-app/snippets/`](src/orders-app/snippets/) | `ordtest.snippet` (Expansion, shortcut `ordtest`, literals `name`, `path`, `status`) and `ordscope.snippet` (SurroundsWith, `$selected$`, literal `step`) |
| [`src/orders-app/src/Contoso.Orders.Api/Properties/launchSettings.json`](src/orders-app/src/Contoso.Orders.Api/Properties/launchSettings.json) | Three profiles: `http` (episode 9's), `Orders API (20 orders, OpenAPI)` (env vars, launch URL, `hotReloadEnabled: true`), `Orders API (no Hot Reload)` |
| [`src/orders-app/tests/Contoso.Orders.Api.Tests/`](src/orders-app/tests/Contoso.Orders.Api.Tests/) | Episode 9's xUnit tests, four of them tagged `[Trait("Category", "Smoke")]`, plus `RunSettingsTests` (passes only when the run settings reached the test host) and [`Smoke.playlist`](src/orders-app/tests/Contoso.Orders.Api.Tests/Smoke.playlist) |
| [`src/orders-app/tools/vs_files.py`](src/orders-app/tools/vs_files.py) | `check` (validates the files above, exit 1 on a problem) and `expand` (what a snippet inserts). Standard library only; `ruff check` and `ruff format --check` clean |
| [`tests/`](tests/) | 48 pytest tests (below) and [`fixtures/`](tests/fixtures/): Learn's published component IDs, the saved real command output used in `script.yaml` |
| `src/orders-app/` (rest) | Episode 9's API and tests unchanged: `Orders.cs`, `Program.cs`, `Reports.cs`, the SQL Server tests (skipped without SQL Server) |

## Run the tests

```bash
cd series/developer-tools/episodes/12-visual-studio-tips-tricks
(cd src/orders-app && dotnet test OrdersApp.Tests.slnf)      # Passed!  - Failed: 0, Passed: 36, Skipped: 4, Total: 40 (the 4 need SQL Server)
(cd src/orders-app && ruff check tools && ruff format --check tools)    # All checks passed! / 1 file already formatted  (ruff 0.16.9)
python3 -m pytest -q tests                                  # 48 passed (about 1.5 minutes on this machine: real builds, test runs, two servers, dotnet watch)
```

Needs .NET SDK 10 (global.json: 10.0.100, rolls forward), Python 3 with `pytest` and `pyyaml`, `ps` (procps) and network access to nuget.org.
The tests restore into one temporary packages folder (`EP12_NUGET_CACHE` to reuse one; about 150 MB) and work on throwaway copies, so
`src/orders-app` never gets `bin/`, `obj/` or a database. Servers and `dotnet watch` run in their own process group and only that group
is killed. One build or test run at a time, `-m:1` where the tests pass it.

| Test file | What it proves |
|---|---|
| `test_vs_files.py` (26) | The repository's own files and the guard. `.vsconfig`: version, the workload and SDK, no duplicates, **every ID is in Learn's published list (saved in `fixtures/`)**, next to the solution; both filters name projects that are in the `.slnx`; `RunSettingsFilePath` is set and `.runsettings` has the values the script shows; the playlist's trait is `Category [Smoke]` and exactly four tests carry it; launch profiles use three distinct ports and the Hot Reload switch; the two snippets are an Expansion and a SurroundsWith. The guard catches: `MaxCPUCount`, a zero timeout, a wrong root element, an unknown and a duplicated component ID, a `.vsconfig` away from the solution, a filter with a foreign project, a missing solution or an empty filter, two profiles on one port, an undeclared and an unused snippet placeholder, `$selected$` twice, a missing `Default`, a reserved ID, a repeated shortcut, a snippet that is not XML. `expand`: defaults, replacements, the selection and `$end$`, a custom delimiter |
| `test_visual_studio.py` (14) | **Real builds and runs.** `dotnet build OrdersApp.Api.slnf` builds the API and creates no `tests/.../bin`; the tests filter builds both projects; `dotnet sln OrdersApp.Api.slnf list` shows only the API; `dotnet build` with no name takes the `.slnx` and builds both. `--filter Category=Smoke --list-tests` lists the four tests the playlist describes. The run settings reach the test host through the property (`RunSettingsTests` passes); **without the property the root `.runsettings` is not auto-detected by `dotnet test` and the test fails with its message**; `--settings .runsettings` fixes it; a filter that matches nothing **fails with the file (exit 1) and passes without it (exit 0)**; the whole suite passes (36 passed, 4 skipped). `TestSessionTimeout` 8000 against a test that sleeps 5 minutes: "test run timeout of 8000 milliseconds exceeded", "Test Run Aborted", in under two minutes. **Launch profile:** the app started with `--launch-profile` answers `"version":"vs-profile"` and 20 orders; with `--no-launch-profile` `"dev"` and 237. **`dotnet watch` Hot Reload:** a method body edit in `Orders.cs` is applied to the running process ("Hot reload succeeded", same process id, no "Exited"); an edit in the top-level statements of `Program.cs` prints "Restart is needed to apply the changes" and the app comes back as a new process with the new text. **Snippets:** both expanded, wrapped in a test class, compiled into the test project: 3 tests pass |
| `test_script.py` (8) | `script.yaml`: header, 15 scenes, 825 words, three shorts, four screens, no markdown; every configuration line on screen is a real line of the real file; every command output line is in `fixtures/command-output.txt` (saved from real runs, paths shortened); the expansion shown is what `expand` prints; the three problem lines shown for the guard are what `check` prints when the three mistakes are made in a copy; the numbers named are the ones the other tests assert |

**Not run here** (Linux build machine, no Visual Studio): everything inside the IDE. The `.vsconfig` prompt and the Installer's
**Import configuration**; opening a `.slnf` that points at an `.slnx` and the funnel glyph; Go To All, Peek, Quick Actions and
multi-caret (shortcuts are copied from Learn's lists, not tried); Code Snippets Manager import and Tab-through of the fields; Test
Explorer opening `Smoke.playlist` (the format is the one Learn shows for xUnit traits; this file has not been opened in Visual Studio);
**Auto Detect runsettings Files** on; the launch-profile drop-down; Hot Reload and Rude-edit behavior in Visual Studio (only
`dotnet watch` was run). All of it is a recording-day check in [demo.md](demo.md).

## What we learned / gotchas

- **`dotnet test` does not auto-detect a `.runsettings` in the solution root.** Learn: Visual Studio auto-detects a file named exactly
  `.runsettings` at the solution root *when the option is on* (Tools > Options > All Settings > Test, or Test > Configure Run Settings). We
  removed the property and the test that reads the environment variable failed with `CONTOSO_REGION is '(not set)'` (tested). The
  `RunSettingsFilePath` property ("Set a build property" in Learn, project or `Directory.Build.props`) is read by `dotnet test` (tested) and by
  Visual Studio (Learn; the IDE side is a recording check). `--settings` on the command line wins over the property (observed: the 8-second
  file replaced the repository's file in the timeout test).
- **A filter that matches nothing is a green run unless you say otherwise.** `dotnet test --filter Category=Nothing` printed "No test
  matches the given testcase filter" and exited **0**; with `TreatNoTestsAsError` in the run settings it exits **1** (tested both).
- **`TestSessionTimeout` is a hard stop, in milliseconds.** The run aborts with "Aborting test run: test run timeout of 8000 milliseconds
  exceeded." / "Test Run Aborted." While preparing this episode it also ended, after the full 5 minutes, a run that had printed `Passed!` after
  6 seconds but was held up by a stale test assembly that still contained the sleeping test: the setting did its job, and the cause was ours.
- **A solution filter is not a solution.** Learn: the `.slnf` still needs the solution file ("The solution file is still required"), and project
  paths in it are relative to the solution. `dotnet build OrdersApp.Api.slnf` works with an `.slnx` and with backslash paths on Linux
  (tested, SDK 10.0.115). Building the tests filter also builds the API because MSBuild follows references (Learn, tested). In a folder
  with the `.slnx` and two filters, `dotnet build` **with no argument builds the `.slnx`** (tested; Learn: "the `.slnx` file takes priority").
  `dotnet sln <file>.slnf list` works on SDK 10; `dotnet sln <file>.slnf add` is documented as .NET 11 and was not tried.
- **net10.0 needs Visual Studio 2026.** Learn: "Targeting `net10.0` is officially supported in Visual Studio 18.0+ only"; SDK 10.0.100 ships with VS
  18.0. The Learn component-ID page we could retrieve is the **Visual Studio 2022 (17.14)** edition and does not list a .NET 10 runtime
  component, so `.vsconfig` names the SDK component (`Microsoft.NetCore.Component.SDK`) and `global.json` pins the SDK version. We could not
  verify the IDs against a Visual Studio 2026 page; the five used are the same names Learn lists for 17.14.
- **Snippet rules from Learn, enforced by the guard:** `$end$` and `$selected$` are reserved (no literal may use them) and may appear once ("only
  the second instance is recognized"); every `Literal` needs exactly one `ID` and one `Default`; a literal that is declared but unused or used
  but not declared is a mistake. In VS 2026 the folder is `Documents\Visual Studio 18\Code Snippets\Visual C#\My Code Snippets`; the
  shortcut works with **Tab twice** in C#; Insert Snippet is **Ctrl+K, Ctrl+X**, Code Snippets Manager **Ctrl+K, Ctrl+B**.
- **Launch profiles and the CLI:** `dotnet run --launch-profile "<name>"` applies `environmentVariables` (tested); the first `Project`
  profile is used by default (Learn). `dotnet run` never opens a browser; `dotnet watch` does for `launchBrowser`, so the test sets
  `DOTNET_WATCH_SUPPRESS_LAUNCH_BROWSER=1`. `hotReloadEnabled: false` turns Hot Reload off per project in Visual Studio (Learn).
- **`dotnet watch` on this shared machine missed edits with the default inotify file watcher** (we did not find out why; many builders
  share the host). `DOTNET_USE_POLLING_FILE_WATCHER=1` (documented by Learn for network shares and containers) made it dependable, and the test
  waits 10 seconds after startup and saves again if no reaction: a save in the first seconds was lost in one run.
- **Top-level statements are a Hot Reload limit** (observed with `dotnet watch`, not documented by us): an edit inside the handlers
  in `Program.cs` printed "Restart is needed to apply the changes", while the same kind of edit inside a method of a normal class was
  applied. Learn's [supported code changes](https://learn.microsoft.com/visualstudio/debugger/supported-code-changes-csharp) page lists what
  is a "rude edit"; we did not read it end to end.
- `dotnet test` prints "VSTEST_ARTIFACTS_DIRECTORY environment variable was not found ... outdated Microsoft.NET.Test.Sdk" even with
  Microsoft.NET.Test.Sdk 18.12.0; the runs pass and we ignored it.
- The blog's "Complete Guide" for this episode was **not compared** line by line (no browser rule); the episode follows the Learn pages below.

## References
- Blog: [Visual Studio Tips & Tricks - Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-21-visual-studio-tips-tricks-complete-guide-2025/)
- Microsoft Learn, install and versions: [Import or export installation configurations](https://learn.microsoft.com/visualstudio/install/import-export-installation-configurations) (`.vsconfig` format, root-of-solution prompt, `--config`, `modify`) ·
  [Visual Studio Community component directory](https://learn.microsoft.com/visualstudio/install/workload-component-id-vs-community) (the IDs; the 17.14 edition) ·
  [Install Visual Studio versions side-by-side](https://learn.microsoft.com/visualstudio/install/install-visual-studio-versions-side-by-side) ·
  [.NET SDK, MSBuild, and Visual Studio versioning](https://learn.microsoft.com/dotnet/core/porting/versioning-sdk-msbuild-vs) (net10.0 needs VS 18.0+) ·
  [Visual Studio release notes](https://learn.microsoft.com/visualstudio/releases/2026/release-notes)
- Microsoft Learn, solutions: [Filtered solutions in Visual Studio](https://learn.microsoft.com/visualstudio/ide/filtered-solutions) (`.slnf`, funnel glyph, loaded count) ·
  [Solution filters in MSBuild](https://learn.microsoft.com/visualstudio/msbuild/solution-filters) (JSON format, relative paths, follows dependencies, `.slnx` takes priority) ·
  [dotnet sln](https://learn.microsoft.com/dotnet/core/tools/dotnet-sln) (`.slnf` support)
- Microsoft Learn, editor: [Shortcut tips](https://learn.microsoft.com/visualstudio/ide/productivity-shortcuts) · [Keyboard shortcuts](https://learn.microsoft.com/visualstudio/ide/default-keyboard-shortcuts-in-visual-studio) ·
  [Go To and Peek Definition](https://learn.microsoft.com/visualstudio/ide/go-to-and-peek-definition) · [Find and replace text](https://learn.microsoft.com/visualstudio/ide/finding-and-replacing-text) (multi-caret)
- Microsoft Learn, snippets: [Use code snippets](https://learn.microsoft.com/visualstudio/ide/code-snippets) ·
  [Walkthrough: Create a code snippet](https://learn.microsoft.com/visualstudio/ide/walkthrough-creating-a-code-snippet) (import, folders, `Shortcut`, Tab twice) ·
  [Code snippets schema reference](https://learn.microsoft.com/visualstudio/ide/code-snippets-schema-reference) (`Literal`, `Default`, `$end$`, `$selected$`, `Delimiter`)
- Microsoft Learn, tests: [Configure unit tests by using a .runsettings file](https://learn.microsoft.com/visualstudio/test/configure-unit-tests-by-using-a-dot-runsettings-file) (auto-detect, `RunSettingsFilePath`, `MaxCpuCount`, `TestSessionTimeout`, `TreatNoTestsAsError`, environment variables) ·
  [Run unit tests by using Test Explorer](https://learn.microsoft.com/visualstudio/test/run-unit-tests-with-test-explorer) (playlists, xUnit trait format)
- Microsoft Learn, running and Hot Reload: [dotnet watch](https://learn.microsoft.com/dotnet/core/tools/dotnet-watch) (rude edits, polling watcher, `DOTNET_WATCH_SUPPRESS_LAUNCH_BROWSER`) ·
  [Configure Hot Reload](https://learn.microsoft.com/visualstudio/debugger/how-to-enable-and-disable-edit-and-continue) (`hotReloadEnabled`, "Enable when not debugging") ·
  [.NET Hot Reload support for ASP.NET Core](https://learn.microsoft.com/aspnet/core/test/hot-reload) ·
  [ASP.NET Core runtime environments](https://learn.microsoft.com/aspnet/core/fundamentals/environments) (`launchSettings.json`, `--launch-profile`)
