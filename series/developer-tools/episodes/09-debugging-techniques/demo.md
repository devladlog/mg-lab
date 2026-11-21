# Demo shot list — DEVLADLOG Dev Tools #9, Debugging techniques

Already real (build machine, 21 Nov 2026): both bugs as patches and what each does (7 `test_bugs` tests), a real `git bisect run` (2 test runs for 6 commits), the
launch configuration's build task and program path, the `.http` requests, JSON logs with scopes and `tools/trace_lines.py`, `scripts/triage-hang.sh` against a really deadlocked
API (`dotnet-stack`, a heap dump, `syncblk`, `clrstack -all`). `dotnet test`: 35 passed, 4 skipped; `pytest`: 35 passed.
**Recorded here for the first time:** VS Code with the C# debugger (breakpoint, Watch, logpoint, conditional breakpoint, Test Explorer), the API as a container on Docker Desktop,
the scripts in Git Bash on Windows, and the dump tools on **Windows** (everything above ran on Linux). Status: **needs the recording laptop**. No Azure, no tenant, no GitHub.

## Lab environment

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows, the lab host) | VS Code with **C# Dev Kit** (`ms-dotnettools.csdevkit`) and **REST Client** (`humao.rest-client`); .NET SDK 10 (`global.json`: 10.0.100, `rollForward: latestFeature`); Git for Windows (Git Bash gives `bash`, `curl`, `tar`, `patch`); Python 3 on the PATH (for `tools/trace_lines.py`); Docker Desktop (WSL 2 backend) for the trace scene; Windows Terminal. All screens are recorded here. | none |
| C# Dev Kit licence | Microsoft Learn (C# Dev Kit, Eligibility): it uses Visual Studio's licence model, free for individuals, academia and open source; **for organizations it is included with Visual Studio Professional and Enterprise subscriptions**. Momento Galático is a company: **check which licence the laptop has before recording**. If there is none: use the open-source *C#* extension (`ms-dotnettools.csharp`) only, which still launches with `launch.json` (replace the Test Explorer screen with `dotnet test` output in the terminal, and say so), or Visual Studio 2022 Community if the licence terms allow it. Decide before recording; do not buy anything for this episode. | none |
| Local tools | `dotnet tool restore` in `src/orders-app` installs `dotnet-stack` and `dotnet-dump` 10.0.750501 from NuGet (pinned in `.config/dotnet-tools.json`). | none |
| Ports | `8080` for the API (the launch configuration, the container and the `.http` file all use it). Stop the container before F5. | none |

Not a Microsoft product, so not from Learn: speedscope is episode 10; here only VS Code and git behaviour come from VS Code's and git's own docs (see README references).

## Prepare (before recording, off camera)

```bash
# Git Bash, from a clone of mg-lab on the laptop. Everything is copied to C:\work so the clone stays clean.
cd series/developer-tools/episodes/09-debugging-techniques
mkdir -p /c/work && cp -r src/orders-app /c/work/orders-debug            # the app, healthy
bash bugs/make-history.sh /c/work/orders-history                          # "history built ... 7 commits, good = demo-good"
cd /c/work/orders-debug && dotnet tool restore && dotnet build src/Contoso.Orders.Api && dotnet test      # 35 passed, 4 skipped
docker build -t contoso/orders-api:dev .                                  # NOT verified on the build machine (no Docker daemon there)
```

Not verified on the build machine: `docker build` of this folder (episode 4's Dockerfile is unchanged and `.dockerignore` keeps `tests/`, `.vscode/`, `.config/` out; the new code is under `src/` and the locked
restore has no new packages), everything that needs Windows, and the VS Code `attach` configuration. If the image build fails, fix it before recording and report it.
Check once, off camera, that the `Debug: Attach to a .NET 5+ or .NET Core process` command works with the configuration "Orders API (attach to a running process)"; if not, say "attach from the Command Palette" instead of showing the file.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/redtest.jpg` — VS Code · Test Explorer**
   - Open `C:\work\orders-debug` in VS Code. In a terminal: `git init -b main && git add -A && git commit -m "feat(reports): monthly revenue per customer"` (so `git apply` and the diff view work), then
     `git apply "$MG/bugs/01-month-end-off-by-one.patch"` (set `MG=<clone>/series/developer-tools/episodes/09-debugging-techniques` once; `git apply` works from the folder it is run in). The Source Control view shows the 5-line change in `Reports.cs`.
   - Testing view (C# Dev Kit): run `MonthEnd_orders_are_part_of_the_month` and `Every_order_lands_in_exactly_one_month`. Capture both red, the message `Expected: 30` / `Actual: 29` (and `237` / `230`), the failing line.
   - Mask: nothing (no accounts).

2. **`screens/debugger.jpg` — VS Code · F5**
   - Same state (patch 01 applied). Run and Debug view → **Orders API (debug)** → F5 (it runs the `build` task first; the API listens on `http://localhost:8080`).
   - Breakpoint on the `var customers = ...` line of `Reports.MonthlyRevenueAsync` (the first line after `ToListAsync`). Open `.vscode/orders.http`, *Send Request* on `GET /reports/monthly?month=2026-01`.
   - Stopped: Variables (`firstDay`, and `lastDay`, the variable the bug introduced), Watch `orders.Count` (29). Debug Console: `orders.Any(o => o.Created == new DateOnly(2026, 1, 31))` → `false`. Hover an `Order` in Variables: the `DebuggerDisplay` text `Order 31: ...`.
   - Right-click the gutter at the `return new MonthlyRevenue(...)` line → *Add Logpoint...* with `{firstDay} has {orders.Count} orders`; right-click the first breakpoint → *Edit Breakpoint* → Expression `firstDay.Month == 1`. Send the January request again, then March (`month=2026-03`): the breakpoint stops only for January, the logpoint prints in the Debug Console without stopping.
   - Then stop the session, revert the bug (`git apply -R ...`), run the two tests: green. Commit: `fix(reports): a month is a half-open range`.

3. **`screens/trace.jpg` — Windows Terminal (Git Bash) · container logs**
   ```bash
   cd /c/work/orders-debug
   docker run --rm -d --name orders-api -p 127.0.0.1:8080:8080 \
     -e Logging__Console__FormatterName=json -e Logging__Console__FormatterOptions__IncludeScopes=true contoso/orders-api:dev
   curl -i -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" "http://localhost:8080/reports/monthly?month=2026-13"
   docker logs orders-api 2>&1 | python tools/trace_lines.py 00-4bf92f3577b34da6a3ce929d0e0e4736-<span id from the response>-01
   docker logs orders-api 2>&1 | tail -n 1        # one raw JSON line with its Scopes array
   ```
   - Capture: `HTTP/1.1 400`, the `traceId` field, the single line `Warning     Contoso.Orders.Reports: Rejected month 2026-13: expected yyyy-MM`, and the raw line with `"TraceId":"4bf92f35..."`.
   - Do it in Git Bash, not PowerShell 5: its pipe re-encodes text and the JSON lines can arrive with a BOM.
   - `docker rm -f orders-api` afterwards.

4. **`screens/hang.jpg` — Windows Terminal (Git Bash) · the hang**
   ```bash
   cd /c/work/orders-debug && git apply "$MG/bugs/02-lock-order-deadlock.patch"      # patch 02 (patch 01 reverted)
   dotnet build src/Contoso.Orders.Api
   ASPNETCORE_URLS=http://localhost:8080 Orders__Cache__HoldMs=50 dotnet src/Contoso.Orders.Api/bin/Debug/net10.0/Contoso.Orders.Api.dll &
   curl -s -m 20 -X POST http://localhost:8080/reports/cache/invalidate & curl -s -m 20 http://localhost:8080/reports/cache &
   curl -s http://localhost:8080/healthz          # still answers: the process is alive
   dotnet tool run dotnet-stack ps                # find the pid of Contoso.Orders.Api
   bash scripts/triage-hang.sh <pid>
   rm -rf triage                                   # the dump: say on camera why
   ```
   - Capture: the two `curl` calls that do not return, `/healthz` that does, then the script output: `threads: N`, the two stuck frames (`Monitor.Enter` under `ReportCache.Invalidate()` and `ReportCache.Snapshot()`), the `syncblk` table with two owners, the two `Reports.cs @ <line>` lines.
   - **Windows is new here**: the script ran on Linux. `dotnet-dump collect` on Windows writes a Windows dump; `syncblk` and `clrstack -all` should read the same. If a step fails in Git Bash, run the commands from the script by hand in PowerShell and fix `scripts/triage-hang.sh` (report it). A dump with heap of this API was 232 MB on Linux: check the free disk space.
   - Stop the API afterwards: `kill <pid>` (Git Bash) or Task Manager.
   - Optional, if Visual Studio is installed: open the dump (File > Open) and show *Parallel Stacks*; Learn's thread-pool page says VS dump debugging offers better visualizations. Not scripted.

## Tear-down

- `docker rm -f orders-api; docker rmi contoso/orders-api:dev`; stop any `Contoso.Orders.Api` process.
- `rm -rf /c/work/orders-debug /c/work/orders-history` (the dumps are inside `triage/` of the first folder: confirm they are gone).
- VS Code: remove the logpoint and breakpoints (Run > Remove All Breakpoints). Leave the extensions.
- Repo working copy: nothing was edited; `git status` must be clean (`bin/`, `obj/`, `.db` files and `triage/` are git-ignored).
