# DEVLADLOG .NET #5 — Testing with xUnit & NUnit: xUnit v3 and NUnit 5 side by side on Microsoft.Testing.Platform

Episode 4's project requests API had **39 tests on xUnit v2 and VSTest**. In this episode the API doesn't change at
all; the tests do:

- **xUnit v2 → xUnit v3 on Microsoft.Testing.Platform (MTP).** `xunit` 2.9.3 → `xunit.v3` 4.0.3 (MTP v2 is its
  default) and `<OutputType>Exe</OutputType>`. All 39 tests compiled and passed unchanged; then analyzer **xUnit1051**
  flagged 50 async calls that didn't pass `TestContext.Current.CancellationToken`. All fixed.
- **The same core tests in NUnit 5** (`NUnit` 5.0.0 + `NUnit3TestAdapter` 6.3.1 with `EnableNUnitRunner`), so you can
  compare the two models on the same code: `[Theory]`/`[InlineData]`/`TheoryData` vs `[TestCase]`/`[TestCaseSource]`
  with NUnit 5's generic `TestCaseData<…>`; class fixtures vs `[OneTimeSetUp]`/`[SetUp]`; `Assert.Equal` vs the
  constraint model, `Assert.EnterMultipleScope`, and NUnit 5's awaitable `Assert.ThrowsAsync`.
- **One `dotnet test` for both**, in the .NET 10 SDK's MTP mode (`global.json`), with framework-specific filters
  routed per project from `Directory.Build.targets`.
- **Opt-in tests against a real SQL Server** (the lab's CON-SQL01): they create a database, apply the SQL Server
  migrations, check behaviour SQLite doesn't have, drop the database — and report **skipped** with the reason when no
  connection string is set. Never a fake green.
- **Coverage** from both apps (Microsoft code coverage extension, Cobertura) merged into one HTML report, plus TRX.

| Path | What it is |
|---|---|
| [`global.json`](global.json) | `"test": { "runner": "Microsoft.Testing.Platform" }` — `dotnet test` in MTP mode (.NET 10 SDK) |
| [`Directory.Build.targets`](Directory.Build.targets) | Appends `$(XunitArgs)` only to xUnit projects and `$(NUnitArgs)` only to NUnit projects |
| [`tests/ProjectRequests.Tests.Xunit/`](tests/ProjectRequests.Tests.Xunit/) | xUnit v3: episode 4's 39 tests migrated + `PriorityRulesTests` (8), `SeededApiTests` (4, class fixture), `SqlServerTests` (2) = 53 |
| [`tests/ProjectRequests.Tests.Xunit/TestCancellation.cs`](tests/ProjectRequests.Tests.Xunit/TestCancellation.cs) | `Ct` = `TestContext.Current.CancellationToken`, imported with `using static` |
| [`tests/ProjectRequests.Tests.NUnit/`](tests/ProjectRequests.Tests.NUnit/) | NUnit 5: `PriorityRulesTests` (8), `ApiTests` (5), `DataTests` (2), `SqlServerTests` (1) = 16 |
| [`tests/ProjectRequests.Tests.NUnit/AssemblySetup.cs`](tests/ProjectRequests.Tests.NUnit/AssemblySetup.cs) | `[assembly: Parallelizable(ParallelScope.Fixtures)]` |
| [`tests/Shared/`](tests/Shared/) | Framework-agnostic helpers linked into both projects: `RequestsApiFactory` (from episode 4), `SqlServerTestDatabase` |
| [`deploy/Invoke-Tests.ps1`](deploy/Invoke-Tests.ps1) | PowerShell 7 runner (Windows laptop or Linux): `All`, `Unit`, `Integration`, `FilterGotcha`, `Coverage`, `SqlServer` |
| `deploy/*.output.txt` | Real output of each mode, captured in the container (paths shortened to `.`) |
| [`dotnet-tools.json`](dotnet-tools.json) | Local tool: ReportGenerator 5.6.1 (merges the Cobertura files) |
| `src/ProjectRequests.Api` | Unchanged from [episode 4](../04-dependency-injection-di-containers/) |

## Build, test, run

```bash
dotnet test                                    # MTP mode via global.json -> total: 69, failed: 0, succeeded: 67, skipped: 2 (~10 s)

pwsh ./deploy/Invoke-Tests.ps1 -Mode Unit      # = dotnet test "-p:XunitArgs=--filter-trait Category=Unit" "-p:NUnitArgs=--filter TestCategory=Unit"
                                               #   -> total: 18 (xUnit 8, NUnit 10)
pwsh ./deploy/Invoke-Tests.ps1 -Mode FilterGotcha   # = dotnet test --filter-trait Category=Unit -> NUnit app: exit code 5
pwsh ./deploy/Invoke-Tests.ps1 -Mode Coverage  # TestResults/*.cobertura.xml + *.trx, coverage-report/index.html
                                               #   -> line coverage 93.4 %, branch 89.2 % (generated code + migrations excluded)

# needs a SQL Server (lab: CON-SQL01) - connection string WITHOUT a database name, never committed:
REQUESTS_TEST_SQLSERVER='Server=10.50.0.30;User ID=requests_tests;Password=...;TrustServerCertificate=True' \
  pwsh ./deploy/Invoke-Tests.ps1 -Mode SqlServer
```

The full run was repeated three times in a row here: 69 / 0 failed / 2 skipped each time. The two skipped tests are
the SQL Server tests (no SQL Server in this container); the SQL Server path is **not verified here** — see demo.md.
Tested with .NET SDK 10.0.115, xunit.v3 4.0.3, NUnit 5.0.0, NUnit3TestAdapter 6.3.1, NUnit.Analyzers 4.15.0,
Microsoft.Testing.Extensions.CodeCoverage 18.12.0, Microsoft.Testing.Extensions.TrxReport 2.5.3, ReportGenerator 5.6.1.

## xUnit v3 vs NUnit 5 — what this project shows

| | xUnit v3 | NUnit 5 |
|---|---|---|
| Test class instances | New instance **per test** | **One** instance per fixture (default `SingleInstance`) |
| Shared setup | `IClassFixture<T>` / collection / assembly fixtures; `IAsyncLifetime` (`ValueTask`) | `[OneTimeSetUp]`/`[OneTimeTearDown]`, `[SetUp]`/`[TearDown]` |
| Parallel by default | Yes: test classes (collections) in parallel, tests in a class sequential | **No** — opt in with `[Parallelizable]` |
| Data-driven | `[InlineData]`, `[MemberData]` + `TheoryData<…>` | `[TestCase]`, `[TestCaseSource]` + `TestCaseData<…>` (generic in 5.0) |
| Run-time skip | `Assert.SkipWhen` / `Assert.SkipUnless` | `Assert.Ignore` (or `Assume.That` → inconclusive) |
| Category / filter on MTP | `[Trait("Category","Unit")]` → `--filter-trait Category=Unit` | `[Category("Unit")]` → `--filter TestCategory=Unit` |
| Cancellation | `TestContext.Current.CancellationToken` (analyzer xUnit1051) | `TestContext.CurrentContext.CancellationToken` |

## What we learned / gotchas

- **One filter option breaks the other framework.** `dotnet test --filter-trait Category=Unit` ran the xUnit app and
  stopped the NUnit app with `Unknown option '--filter-trait'`, **exit code 5** (`deploy/filter-gotcha.output.txt`).
  Learn documents exactly this and the fix: conditional `TestingPlatformCommandLineArguments`.
- **…and the fix silently does nothing from `Directory.Build.props`.** We tried it there first: no error, no filter —
  all 69 tests ran. `XunitTestProject` comes from the xunit.v3 package's props and `EnableNUnitRunner` from the project
  file; both are evaluated *after* `Directory.Build.props`, so the conditions are false. In `Directory.Build.targets`
  the same lines work (18 tests).
- **XML comments can't contain `--`.** Putting the command line in a comment in `Directory.Build.targets` breaks every
  build: `error MSB4024: ... An XML comment cannot contain '--'`. The command lives in this README and in
  `Invoke-Tests.ps1` instead.
- **The v2 → v3 migration was two lines + 50 warnings.** No API change was needed in these 39 tests (no
  `IAsyncLifetime` or custom attributes in them); xUnit1051 then flagged every call that could take the test's
  cancellation token. New v3 code: `IAsyncLifetime` returns `ValueTask` and disposal comes from `IAsyncDisposable`.
- **NUnit 5's `Assert.ThrowsAsync` must be awaited.** Without `await`, NUnit.Analyzers 4.15 fails the build:
  `error NUnit2059: Method 'ThrowsAsync' returns a Task and is not being observed`.
- **NUnit shares one instance across a fixture's tests**, so fields are shared state: `DataTests` opens its in-memory
  SQLite connection in `[SetUp]`, not in a field initializer. In xUnit the same field initializer is per test.
- **Decimals in attributes:** C# attributes can't take `decimal`; both `[InlineData(49_999.99, …)]` and
  `[TestCase(49_999.99, …)]` pass a double and both frameworks converted it to the `decimal` parameter correctly.
- **The test that can't run here found a bug in the helper that can.** `SqlServerTestDatabase` first cut the database
  name with `[..60]` — on a 54-character name that throws. The SQL Server tests are skipped in the container, so we added
  `Each_run_gets_its_own_database_and_keeps_the_server_settings`, which needs no server; it caught it.
- **Coverage shows decimal constants as missed lines.** `PriorityRules` reports 50 % although both methods are tested:
  a `const decimal` isn't an IL literal — the compiler emits a static readonly field with `DecimalConstantAttribute`,
  set in a static constructor (we checked with reflection). Callers inline the value, nothing reads the field, and the
  two declaration lines show 0 hits.
- **Generated code drags coverage down.** The raw merged report said 44.8 %: source-generated OpenAPI/validation
  classes and EF migrations count as coverable lines. Excluding `Microsoft.*` and `ProjectRequests.Api.Migrations.*`
  in ReportGenerator gives 93.4 %. Say what you exclude.
- **Don't mix VSTest and MTP projects in one solution** (unsupported, per Learn). Both projects here are MTP; there's no
  `Microsoft.NET.Test.Sdk` in either. `coverlet.collector` doesn't work with the NUnit runner — we use the Microsoft
  code coverage extension in both.

## References
- [Testing with `dotnet test`: VSTest mode, MTP mode (global.json), mixed frameworks and `TestingPlatformCommandLineArguments`](https://learn.microsoft.com/dotnet/core/testing/unit-testing-with-dotnet-test)
- [Test platforms overview (don't mix VSTest and MTP; IDE support)](https://learn.microsoft.com/dotnet/core/testing/test-platforms-overview)
- [MTP support in NUnit (NUnit runner): `EnableNUnitRunner`, `OutputType Exe`, NUnit3TestAdapter 5.0+, coverlet note](https://learn.microsoft.com/dotnet/core/testing/unit-testing-nunit-runner-intro)
- [Migrate from VSTest to MTP (xUnit.net filter options, `--coverage`)](https://learn.microsoft.com/dotnet/core/testing/migrating-vstest-microsoft-testing-platform)
- [MTP code coverage (`--coverage`, `--coverage-output-format cobertura`, `IncludeTestAssembly` default)](https://learn.microsoft.com/dotnet/core/testing/microsoft-testing-platform-code-coverage)
- [Use code coverage for unit testing](https://learn.microsoft.com/dotnet/core/testing/unit-testing-code-coverage)
- [MTP: run and debug tests (VS Code Test Explorer with C# Dev Kit)](https://learn.microsoft.com/dotnet/core/testing/microsoft-testing-platform-run-and-debug)
- [MTP overview: MSBuild integration, auto-registered extensions](https://learn.microsoft.com/dotnet/core/testing/microsoft-testing-platform-intro)
- [Server-level roles (`dbcreator`)](https://learn.microsoft.com/sql/relational-databases/security/authentication-access/server-level-roles)
- xUnit.net: [Shared context / fixtures](https://xunit.net/docs/shared-context), [Running tests in parallel](https://xunit.net/docs/running-tests-in-parallel), [xunit.v3 4.0.0 release notes (MTP v2 default)](https://xunit.net/releases/v3/4.0.0)
- NUnit: [5.0 release notes (awaitable ThrowsAsync, generic TestCaseData)](https://docs.nunit.org/articles/nunit/release-notes/framework.html), [Parallelizable](https://docs.nunit.org/articles/nunit/writing-tests/attributes/parallelizable.html), [FixtureLifeCycle](https://docs.nunit.org/articles/nunit/writing-tests/attributes/fixturelifecycle.html)
- Blog: [Testing with xUnit & NUnit — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-23-testing-with-xunit-nunit-complete-guide-2026/) (the current article is generic and should be replaced with this episode's code)
