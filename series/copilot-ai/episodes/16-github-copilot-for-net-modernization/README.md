# DEVLADLOG Copilot & AI #16 - GitHub Copilot for .NET Modernization

Contoso Bikes' dealer quote service still runs on .NET Framework 4.7.2: a class library with Newtonsoft.Json and the old
SQL client, an ASP.NET MVC 5 web app, and a test project, all in the legacy project format with `packages.config`. This
episode lets **GitHub Copilot upgrade** (Microsoft Learn's current name; it was *GitHub Copilot app modernization for
.NET*) upgrade it to .NET 10 for real in Visual Studio, and builds the pieces around it that make the result checkable:

- a **pre-scan** of a solution (what the agent will meet, mapped to the scenario and skill names Learn lists, upgrade order);
- a **characterization test set** that runs against the legacy sources, a hand-written reference upgrade, a naive
  find-and-replace upgrade (which fails on purpose) and, at recording time, the agent's own output;
- a checker for the state the agent keeps in `.github/upgrades/{scenarioId}/`;
- a **custom upgrade instruction** (`replace_newtonsoft_with_system_text_json.md`) and a linter for Learn's authoring tips.

The upgrade itself (Visual Studio, Copilot, the model) cannot run here: it is recorded on the lab laptop (`demo.md`).
Nothing in this folder pretends to be Copilot output; `src/expected-after` is hand-written and labelled as such.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Category episodes this builds on:
[Entity Framework Core](../../../net/episodes/03-entity-framework-core/) and [.NET 8/9 features](../../../net/episodes/10-net-8-9-features/).
Previous: episode 15, [Coding agent and code review](../15-github-copilot-coding-agent-and-code-review/) (its Learn-linked
install page shows this same upgrade agent running as a cloud-agent custom agent).

| Path | What it is |
|---|---|
| [`src/legacy-contoso/`](src/legacy-contoso/) | The legacy solution (fictional): `Contoso.Pricing` (Newtonsoft.Json 12.0.3, `System.Data.SqlClient`), `Contoso.Pricing.Tests` (NUnit 3), `Contoso.Orders.Web` (MVC 5, Global.asax, `HttpContext.Current`, `Session`), all `net472`, old project format, `packages.config`. Placeholder GUIDs and password |
| [`src/legacy-contoso/upgrade-instructions/replace_newtonsoft_with_system_text_json.md`](src/legacy-contoso/upgrade-instructions/replace_newtonsoft_with_system_text_json.md) | Custom upgrade instruction in the shape Learn describes (detect, if/then steps, a diff from a real edit) |
| [`src/legacy-contoso/sql/001-price-list.sql`](src/legacy-contoso/sql/001-price-list.sql) | Lab database `contoso_pricing` with three fictional SKUs; login and password are created at the console, never stored |
| [`src/expected-after/Contoso.Pricing/`](src/expected-after/Contoso.Pricing/) | **Hand-written** reference upgrade of the library: SDK-style `net10.0`, System.Text.Json, Microsoft.Data.SqlClient 7.1.2 |
| [`src/expected-after/Contoso.Pricing.Probe/`](src/expected-after/Contoso.Pricing.Probe/) | Console that reads one list price through `PriceListRepository` (needs `CON-SQL01`); used for the TLS screen |
| [`src/naive-after/QuoteSerializer.cs`](src/naive-after/QuoteSerializer.cs) | What a quick find-and-replace of `JsonConvert` with `JsonSerializer` gives |
| [`src/ModernizationScan/`](src/ModernizationScan/) | .NET 10 console: `scan`, `check-upgrade`, `lint-instruction` (`Scanner.cs`, `Rules.cs`, `UpgradeFolder.cs`, `InstructionLint.cs`, `ReportWriter.cs`) |
| [`tests/ModernizationScan.Tests/`](tests/ModernizationScan.Tests/) | 40 xunit tests |
| [`tests/Pricing.Characterization/`](tests/Pricing.Characterization/) | 14 behaviour tests run against `-p:Impl=legacy`, `modern`, `naive` or `agent -p:AgentDir=<folder>` |
| [`tests/test_script.py`](tests/test_script.py) | 4 pytest checks: script header, scene shape, narration length, code excerpts exist in the repo |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes) and recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/16-github-copilot-for-net-modernization
dotnet test tests/ModernizationScan.Tests -m:1                                     # 40 passed
dotnet test tests/Pricing.Characterization -m:1 -p:Impl=legacy                     # 13 passed (Newtonsoft.Json, as today)
dotnet test tests/Pricing.Characterization -m:1 -p:Impl=modern                     # 14 passed (reference upgrade; 1 lab-helper test)
dotnet test tests/Pricing.Characterization -m:1 -p:Impl=naive                      # 5 failed, 8 passed: the point of the demo
dotnet test tests/Pricing.Characterization -m:1 -p:Impl=agent -p:AgentDir=$PWD/src/expected-after/Contoso.Pricing   # 13 passed
python3 -m pytest -q                                                               # 4 passed
cd src
dotnet run --project ModernizationScan -- scan legacy-contoso                      # Markdown report (--md/--json to files)
dotnet run --project ModernizationScan -- scan expected-after                      # 2 projects, score 0, no findings
dotnet run --project ModernizationScan -- lint-instruction legacy-contoso/upgrade-instructions/replace_newtonsoft_with_system_text_json.md
dotnet run --project ModernizationScan -- check-upgrade <repo>                     # after the agent ran: stage and task counts
```

Verified here (.NET SDK 10.0.115, Linux, Python 3.13): the counts above. The legacy C# sources also compile against the
.NET Framework 4.7.2 reference assemblies with `Microsoft.AspNet.Mvc` 5.2.9 and `Newtonsoft.Json` 12.0.3 (a throwaway
SDK-style project in a temp folder; it found one real bug in the first draft of the controller, now fixed).
**Not verified here:** the old-style `.csproj`/`.sln` files opening and building in Visual Studio (they need Windows and
MSBuild's .NET Framework targets), the NUnit tests running in Visual Studio, the agent itself, the SQL scripts and
`Contoso.Pricing.Probe` against SQL Server (compile only; its failure path was run against a closed port), and
`check-upgrade` on real agent output (tested on the task-list format that Learn shows).

## What we learned / gotchas

- **The name changed again.** Learn's pages are titled *GitHub Copilot upgrade* and the Visual Studio component is still
  called *GitHub Copilot app modernization*; the menu entry is **Modernize**, the chat handles are `@Modernize` (Visual
  Studio) and `@upgrade` (VS Code, Copilot CLI). The older **.NET Upgrade Assistant** is "officially deprecated in favor
  of" the agent (Learn, .NET porting overview).
- **Three stages, saved in Git.** `assessment.md`, `upgrade-options.md`, `plan.md`, `scenario-instructions.md`, `tasks.md`
  under `.github/upgrades/{scenarioId}/`; per-task `tasks/{taskId}/task.md` and `progress-details.md`. Learn suggests committing
  the folder so a teammate (or another IDE) can continue. The agent commits as it goes, so the project must be in Git.
- **Editing the plan can break it.** Learn's caution: if Project A depends on Project B and you remove B from the plan,
  A's upgrade might fail.
- **Newtonsoft to System.Text.Json is not a find-and-replace** (reproduced here, `Impl=naive`): default System.Text.Json
  is case-sensitive, writes PascalCase and enums as numbers, does not read numbers from strings, and throws on empty input
  where Newtonsoft returned null. `JsonSerializerDefaults.Web` fixes the first four; the empty-input guard is explicit code.
- **Microsoft.Data.SqlClient encrypts by default** (Learn: starting with version 4.0): a server with only SQL Server's
  self-signed certificate fails with a certificate-chain error. `TrustServerCertificate=true` is for controlled development
  environments only; Learn says not to use it as a general migration fix. Also, `SqlConnectionStringBuilder.Encrypt`
  changed from `bool` to `SqlConnectionEncryptOption` in 5.0 (binary breaking: recompile). The expected failure against
  `CON-SQL01` is what Learn documents; we have not yet seen it on the lab server.
- **The harness needs a newer Newtonsoft than the fixture.** The xunit test host requires Newtonsoft.Json 13.0.1 or later,
  so the characterization harness uses 13.0.3 for the legacy implementation. The fixture itself keeps 12.0.3, which
  restore reports as having a known high-severity vulnerability (NU1903): a realistic finding for the assessment.
- **The reference upgrade only compiled because of the harness at first.** It lacked `ImplicitUsings` and built inside the
  harness (which enables them) but not as its own project; `-p:Impl=agent` (project reference) caught it. Test the
  artifact, not only the copy.
- **Visual Basic is not fully supported** by the modernization agent (guardrails built for C#): Learn points to the standard
  Copilot agent or the Upgrade Assistant. Mixed C# and VB solutions can use the agent for the C# projects.
- **Targets and platforms.** The agent upgrades to .NET 8 or later (or to .NET Framework 4.8.1); Learn's examples use .NET 10
  (LTS). Visual Studio needs Windows, Visual Studio 2026 or 2022 17.14.17+; VS Code, Copilot CLI and the GitHub Copilot app
  are other entry points. Learn's install page requires "a GitHub Copilot subscription (paid or free)".
- **Our scan score is our own heuristic**, not a Microsoft measure, and the strategy hint is only a starting point: the
  agent proposes its own (bottom-up, top-down or all-at-once) in `upgrade-options.md`.

## References

- Upgrade .NET projects with GitHub Copilot (overview): <https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/dotnet-overview>
- Upgrade a .NET app with GitHub Copilot upgrade: <https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/dotnet-how-to-upgrade-with-github-copilot>
- .NET scenarios and skills: <https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/dotnet-scenarios-and-skills>
- Apply custom upgrade instructions: <https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/dotnet-how-to-custom-upgrade-instructions>
- GitHub Copilot upgrade concepts: <https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/concepts>
- Install GitHub Copilot upgrade: <https://learn.microsoft.com/dotnet/core/porting/github-copilot-app-modernization/install>
- Overview of upgrading .NET apps (Upgrade Assistant deprecated): <https://learn.microsoft.com/dotnet/core/porting/>
- Languages and frameworks supported by GitHub Copilot modernization: <https://learn.microsoft.com/azure/developer/github-copilot-app-modernization/languages>
- Upgrade a WPF app with GitHub Copilot modernization (Visual Basic note, .NET Framework 4.5 retarget prompt): <https://learn.microsoft.com/dotnet/desktop/wpf/migration/how-to-upgrade-wpf>
- Migrate from System.Data.SqlClient to Microsoft.Data.SqlClient: <https://learn.microsoft.com/sql/connect/ado-net/migrate-system-data-sql-client-to-microsoft-data-sql-client>
- Encryption and certificate validation in Microsoft.Data.SqlClient: <https://learn.microsoft.com/sql/connect/ado-net/encryption-and-certificate-validation>
- No blog Complete Guide: this series is built from official documentation only.
