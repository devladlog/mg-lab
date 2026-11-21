# Demo shot list - DEVLADLOG Dev Tools #12, Visual Studio tips and tricks

Already real (build machine, Linux, 21 Nov 2026): every file, command and output on the `code` scenes of `script.yaml`:
the solution filters built with `dotnet build`, the `.runsettings` file (environment variable, `TreatNoTestsAsError`, `TestSessionTimeout`)
through `dotnet test`, the root `.runsettings` that `dotnet test` does not pick up, the two code snippets expanded and compiled into
passing tests, the launch profile's environment, `dotnet watch` Hot Reload (a method edit applied without a restart, a top-level edit
that needs one), and `tools/vs_files.py` (see README for the test counts).
**Recorded here for the first time, on Windows:** everything that happens inside Visual Studio itself: the missing-components prompt
for `.vsconfig`, opening a `.slnf`, Go To All / Peek / Quick Actions / multi-caret, importing and using the snippets, Test Explorer with
the playlist and the run settings menu, the launch profile drop-down and Hot Reload in the IDE.
Status: **needs the Windows recording laptop with Visual Studio. No Microsoft 365 tenant, no Azure subscription, no Azure DevOps, no sign-in
beyond the Visual Studio account prompt (skip it: "Skip this for now").**

## Lab environment

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows 11, x64) | **Visual Studio 2026** (version 18.x, Community is enough) with the **ASP.NET and web development** workload, installed **side by side** with Visual Studio 2022 if that is already there (Learn: they coexist). Visual Studio 2026 ships with .NET SDK 10.0.100 or later, which `global.json` asks for (and rolls forward). Windows Terminal (PowerShell 7) · **git** · **Python 3.10 or newer** (`python`, only for `tools/vs_files.py`). | none (Community edition) |
| The repository | `series/developer-tools/episodes/12-visual-studio-tips-tricks/src/orders-app`, copied to `C:\demo\orders-app` (a short path: the build creates long ones). Contoso Orders API from episodes 4 to 11, fictional data only. | none |
| Accounts | None. When Visual Studio asks for a Microsoft account at first start, choose **Skip this for now**, so no account name appears in the title bar or the account menu. No tenant, no cloud resource. | none |
| Network | nuget.org only (first restore, about 100 MB of packages). The Visual Studio Installer needs the internet for the `.vsconfig` demonstration. | none |

Nothing in this folder contains an organization, tenant or user name. The recording user is `Alex Demo`; the repo, the customers (Contoso
Retail, Fabrikam, ...) and the region `lab-west` are fictional. **Mask** the Windows user name in every path (use `C:\demo\...` and a
terminal prompt of just `PS C:\demo\orders-app>`), the machine name in the title bar of the Installer, and any account picture.

## Setup (off camera, in this order)

1. Install Visual Studio 2026 with the **ASP.NET and web development** workload (Installer -> Modify). Then **remove two things on
   purpose**, so that the `.vsconfig` prompt has something to offer: in the Installer, **Modify -> Individual components**, untick
   **.NET profiling tools** (`Microsoft.VisualStudio.Component.DiagnosticTools`) and **IntelliCode** (`Microsoft.VisualStudio.Component.IntelliCode`).
   Close the Installer and Visual Studio.
2. Copy the folder and restore once, so the demo is not waiting for NuGet (PowerShell):

```powershell
$mg = "<path-to>\mg-lab\series\developer-tools\episodes\12-visual-studio-tips-tricks"
robocopy "$mg\src\orders-app" C:\demo\orders-app /E /XD bin obj .nuget /NFL /NDL /NJH /NJS
cd C:\demo\orders-app
git init -q; git add -A; git commit -qm "chore: import orders api"
dotnet restore OrdersApp.slnx
python tools\vs_files.py check . --known-ids "$mg\tests\fixtures\learn-component-ids.txt"    # all Visual Studio files are consistent
```

3. Visual Studio, **before recording**: Tools > Options > All Settings > **Test** > untick **Auto detect runsettings files**
   (the shot 6 demonstration turns it on). Tools > Options > All Settings > **Debugging** > **.NET/C++ Hot Reload** > tick
   **Enable when not debugging** (Learn: this is what makes Hot Reload work with Ctrl+F5). Font size 16 or more, zoom 125 %.
4. Windows: turn off notifications (Focus assist), close other windows, hide the Windows taskbar clock if it shows a time zone.

## Shots (the four `screen` scenes of script.yaml, in order; capture each as a JPEG into `screens/`)

| # | Scene id | What to capture | Take |
|---|---|---|---|
| 1 | `vsopen` | Open `C:\demo\orders-app` by double-clicking **`OrdersApp.Api.slnf`**: Solution Explorer shows the funnel glyph and the name with **1 project loaded** (Learn: "the name of the filter and the number of loaded projects"). Then close, open **`OrdersApp.slnx`**: because `.vsconfig` sits in the solution root, the yellow bar **"Some components are missing ..."** appears (Learn: Visual Studio detects missing components and prompts to install). Click **Install** only in the second take, off camera. Capture the bar with the two component names visible. | Mask the Windows user in the title bar and recent list. |
| 2 | `nav` | In `Orders.cs`, **Ctrl+T** (Go To All), type `Paging`; **F12** on `Normalize`, then **Alt+F12** (Peek Definition) on `Clamp`; **Ctrl+.** on `Paging.Normalize(page, pageSize)` in `Program.cs` (Quick Actions); multi-caret: select `"customer"`, press **Shift+Alt+.** twice, type; and **Ctrl+Alt+click** on two lines. Capture Go To All with results, the Peek window, and the carets. | All shortcuts are from the Learn "Shortcut tips" and "Keyboard shortcuts" pages; if a binding differs in your profile, say so on camera. |
| 3 | `testexplorer` | **Ctrl+E, T** (Test Explorer), group by Traits; playlist button -> open **`tests\Contoso.Orders.Api.Tests\Smoke.playlist`**: four tests (including `The_repository_runsettings_reached_the_test_host`); **Ctrl+R, T** (run all in context). Then **Test > Configure Run Settings**: show **Auto Detect runsettings Files** off and, in the Test Explorer output, the test passing because `RunSettingsFilePath` is set. | Do the demonstration of "auto detect" separately: turn it on, delete the `<RunSettingsFilePath>` line temporarily, run again (see Checks). |
| 4 | `hotreload` | In the toolbar choose the profile **Orders API (20 orders, OpenAPI)**, **Ctrl+F5**: the browser opens `openapi/v1.json`. In `Orders.cs` change `1` to `2` in `Math.Clamp(pageSize ?? DefaultPageSize, 1, MaxPageSize)`, click **Hot Reload** (the flame), refresh `http://localhost:8081/orders?pageSize=1`: `"pageSize":2`. Then edit the string `"ok"` in `Program.cs`'s `/healthz` handler and note what Visual Studio says. | The browser address bar shows `localhost` only. Close other tabs. |

The code scenes (`vsconfig`, `slnf`, `snippet`, `runsettings`, `gotcha`, `profile`, `guard`) are recorded in Visual Studio Code-style
dark theme from the files in the repository, or as terminal output on the build machine: nothing to stage.

## Checks to make during recording (what this folder could not verify on Linux)

- **`.vsconfig` prompt:** it appears when the solution (the `.slnx`, or the filter) is opened and a component from the file is missing.
  The component IDs in the file are all in Learn's published list for Visual Studio **2022 (17.14)**; the Learn page for Visual Studio
  2026 was not retrievable here, so confirm that the Installer's **Import configuration** (More > Import configuration > pick the file >
  Review details) lists exactly the five entries and no "unknown component" warning.
- **Opening a `.slnf` with a `.slnx`:** the filter points at `OrdersApp.slnx`. The build side is tested (`dotnet build` works); whether
  Visual Studio 2026 loads the one project and shows the funnel for an `.slnx`-based filter is **not** tested here.
- **Run settings:** with **Auto detect runsettings files** on and the `<RunSettingsFilePath>` line removed, Test Explorer should pass
  `The_repository_runsettings_reached_the_test_host` because the root `.runsettings` is detected (Learn), while `dotnet test` fails it
  (tested). If Test Explorer fails it too, say so: that is the finding.
- **Hot Reload edits:** note exactly what Visual Studio does for the `Program.cs` edit. With `dotnet watch` on Linux the edit needed a
  restart ("Restart is needed to apply the changes", tested); Visual Studio may offer "Rebuild and Apply" or behave differently.
- **Snippets:** Tools > Code Snippets Manager (**Ctrl+K, Ctrl+B**) > Language **Visual C#** > **Import** both files from `snippets\` >
  folder **My Code Snippets**. Open `ApiTests.cs`, in the class body type `ordtest`, **Tab**, **Tab**: three fields (`name`, `path`,
  `status`), **Tab** moves between them, **Enter** ends. For `ordscope` select two statements, **Ctrl+K, Ctrl+S** (Surround With) or
  Edit > IntelliSense > Surround With. Learn says the snippet is copied to `Documents\Visual Studio 18\Code Snippets\Visual C#\My Code Snippets`.
  The expansion text itself is tested (it compiles and the three tests pass).
- **Launch profile drop-down:** the three profile names appear in the toolbar; `applicationUrl` ports 8080, 8081 and 8082 must be free.

## Masking

- Windows user name in paths, the title bar, the recent-projects list and the Installer: use `C:\demo\...` and a clean profile.
- No Microsoft account picture or name (skipped sign-in). No GitHub or Azure DevOps account in the Accounts settings.
- Nothing from `%USERPROFILE%` on screen; the snippet folder under `Documents\Visual Studio 18\` is shown as `...\Documents\Visual Studio 18\...`.

## Tear-down

1. Visual Studio: close the solution; File > Clear recent items. Installer: **Modify**, put the two removed components back if the laptop is also used for other work.
2. Delete `C:\demo\orders-app` (Explorer, or PowerShell `Remove-Item -Recurse -Force C:\demo\orders-app`).
3. Tools > Code Snippets Manager: remove the two imported snippets (`ordtest`, `ordscope`) from **My Code Snippets**.
4. Nothing was created in any cloud service, tenant or subscription, so there is nothing else to delete.
