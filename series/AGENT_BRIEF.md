# Brief for episode builders (DEVLADLOG category series)

You are preparing **draft episodes** for a YouTube series by Momento Galático, a Microsoft consultancy in Portugal.
Each series covers one category of the blog devladlog.com; each episode covers one blog topic.
Your job: for each episode assigned to you, produce **working, tested material + a draft video script + a demo shot list**.
A human-supervised session will later record the real demo in a lab tenant, render and publish. You do none of that.

Repo root: `/home/claude/mglab/mg-lab`. Look at these as the quality reference before you start:
- `episodes/07-pcf-code-component/` (script.yaml, README.md, src/ with tests) — the gold standard
- `episodes/06-sharepoint-migration-pnp/` and `episodes/04-dataverse-plugin-csharp/`
- `pipeline/make_episode.py` — the renderer that reads `script.yaml` (scene types: `title`, `bullets`, `code`, `screen`, `outro`)
- `series/series.yaml` and `series/<slug>/README.md` — the series plan (audience, what's needed)

## Hard rules
1. **Write only inside your assigned episode folders.** Never edit other files. **Do not run git commit/push.**
2. **No browser, no Metricool, no YouTube, no social posting, no sign-ins, no cloud resources created**, no `az login`,
   no device codes. Work entirely in the local container (Bash, file tools, web search/fetch for docs).
3. **Every code sample must actually run here** (build, lint, unit tests, or a local emulator/container). If a step
   genuinely needs the tenant (Dataverse, SharePoint, Entra, M365 admin), still write the real code/script, validate
   what you can locally (syntax check, `--help`, unit tests with mocks, `bicep build`, `dotnet build`, `npx tsc`,
   `pwsh -NoProfile -Command { [ScriptBlock]::Create(...) }`, `python -m py_compile`), and mark it "needs tenant" in demo.md.
   **No placeholder scripts that just print messages.** That is exactly the problem we are fixing on the blog.
4. **Verify facts against Microsoft Learn** (use the Microsoft Learn tools or WebFetch on learn.microsoft.com):
   limits, licensing, feature names, retirement dates, cmdlet/API names. Put the URLs in README "References".
   If something can't be verified, leave it out.
5. **Confidentiality:** never use client names or real identifiers. Use `contoso`, `Alex Demo`, fictional data,
   zero GUIDs. Never write the real tenant name (devladlog) or real URLs of the lab tenant.
6. Don't install heavy system packages if avoidable; `pip --break-system-packages`, `npm`, `dotnet` are fine.
   Toolchains present: .NET 8 + 10, Node 22, Python 3 + pytest, PowerShell 7.6 (`pwsh`) + Pester, Bicep CLI (`bicep`),
   pac CLI (`pac`, not signed in), ffmpeg. **Do not use apt** and do not install global tools (other builders run in
   parallel in the same container); install per-project (npm in your folder, pip --user, NuGet per project).
   Docker is not available: for SQL use SQLite or a pure-Python/.NET equivalent when you need to execute queries,
   and state that in README.
7. Keep each episode folder under ~5 MB. No binaries, no node_modules, no bin/obj (they're gitignored, but don't leave
   huge folders: delete node_modules after testing).

## Deliverables per episode (folder given in your assignment; overwrite any stub there)
- `README.md` — like episode 07's: what we build, table of files, how to run/test, "What we learned / gotchas"
  (only real ones you hit or that Learn documents), References (Learn URLs + the blog Complete Guide URL).
- `src/` (and `tests/` or test project) — the working material. Tests must pass; put the exact command + result
  count in README.
- `script.yaml` — draft video script for `pipeline/make_episode.py`, 12–16 scenes, ~5–6 minutes of narration
  (≈ 750–900 words total). Header fields:
  ```yaml
  episode: <n>
  slug: <folder name without the NN- prefix>
  series_label: "<LABEL>"
  series_name: "<Series name>"
  file_prefix: "<series slug>"
  title: ...
  subtitle: ...
  voice: am_michael
  thumbnail_text: "LINE1\nLINE2\nLINE3"
  youtube: {title: "<= 100 chars, no < or >, ends with | <Series name> #<n>", tags: [...]}
  sources: [<blog Complete Guide URL>]
  ```
  Scenes: open with a `title` hook (`short: hook`), mostly `code` (real excerpts from your src, ≤ 16 lines each) and
  `bullets`, plus 3–5 `screen` scenes for the live demo with `image: screens/<name>.jpg`, `bar: "<context>"` and a
  `demo:` field describing exactly what must be on screen (the recorder will capture it). Mark exactly 3 scenes with
  `short: <id>` (good stand-alone 20–40 s moments). Include one honest "gotcha" scene. End with `type: outro`,
  `heading: "Code on GitHub, guides on devladlog.com"`, `sub: "github.com/devladlog/mg-lab"`.
  Narration: plain spoken English, no markdown, no emoji, spell out symbols ("dot net", "p n p"), say numbers as words
  when ambiguous. Never claim something you didn't verify.
- `demo.md` — shot list for the recorder: prerequisites (licences/trials/resources, cost), exact steps to set up
  in the lab tenant, each screen to capture (matching the `screen` scenes), masking notes, tear-down steps.
  **Demos must be real.** Every `screen` scene shows the real product doing the real thing (your code running against
  the real service, the real portal, a real VM). Never plan a screen around a mock, stub, fake server or local
  stand-in; those are only for your automated tests. If a demo needs infrastructure, start demo.md with a
  `## Lab environment` section that lists it precisely so it can be provisioned: each VM (role, OS + edition,
  vCPU/RAM/disk, network/domain, software to install), containers, Azure resources, licences/trials, and which
  machine the screens are recorded on (lab Windows desktop, lab VM console, browser on the lab tenant). Prefer
  evaluation/developer editions and the shared lab VMs listed in `series/LAB.md` (read it if present).

## Report back (your final message, ≤ 15 lines)
For each episode: folder, what was built, test command + result (e.g. "dotnet test: 12 passed"), what needs the
tenant, anything you could not verify or finish. Be honest: a partial episode clearly marked is fine; a fake one is not.

## Shared machine (important)
The container has 2 CPUs and ~7 GB RAM shared by ~8 builders at a time. Keep it light: one build/test at a time,
`dotnet build -m:1`, `npm ci --no-audit --no-fund`, kill any server you start, delete `node_modules`, `bin`, `obj`
when done. Don't start long-running containers. If a build gets OOM-killed, retry once later, then report it.

## PowerShell / Pester gotchas (learned)
- Under `-WhatIf`, `ForEach-Object <propName>` prints "What if: Retrieve..." and returns nothing; use script blocks inside functions that support `-WhatIf`.
- Pester 5+: a function defined in a `Describe` body is not visible inside `It`; define helpers in the top-level `BeforeAll`.
- Mocks of PnP.PowerShell cmdlets need a real `PnPConnection` instance (`RuntimeHelpers.GetUninitializedObject`) and pipe-bind types (read `$Site.Url`).
- .NET: xUnit v3 on Microsoft.Testing.Platform needs `dotnet test --project <csproj>` (`-m:1` is rejected there). The MAUI XAML source generator runs on Linux without the maui workload (plain net10.0 + Microsoft.Maui.Controls PackageReference, no UseMaui).
- Pester: mocks cannot fill `-ResponseHeadersVariable` in the caller's scope; mock the wrapper one level up.
