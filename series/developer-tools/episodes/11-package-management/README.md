# DEVLADLOG Dev Tools #11 - Package management: versions, sources and vulnerabilities in files

The orders API from [episode 6](../06-code-quality-tools/) gets three package decisions written into the repository
instead of living in people's heads: **who decides each version** (NuGet Central Package Management plus lock files),
**which source may serve which package** (package source mapping) and **what counts as a vulnerability** (NuGet Audit, a
small report tool, and one pipeline job that is allowed to fail on it). The shared DTOs and validation rules move into a
library, `Contoso.Orders.Contracts`, that an Azure Pipelines run publishes to an **Azure Artifacts** feed and a second
repository consumes. The Python tools get hashes instead of a hand-written pin.

```
 repo  ──► Directory.Packages.props   one version per package, transitive pinning on, per-project overrides off
       ──► packages.lock.json         (episode 5) must change in the same commit as the central file
       ──► Directory.Build.props      NuGet Audit warnings stay warnings; errors only with -p:AuditPipeline=true
       ──► tools/pkg_audit.py         dotnet package list --format json  ->  text / markdown / ##vso annotations
 CI    ──► azure-pipelines.yml        build job: locked restore, build, test, audit (warn), pack, push to the feed
                                      audit job: restore with audit errors + pip install --require-hashes + pip-audit
 feed  ──► Azure Artifacts            contoso-packages: Contoso.Orders.Contracts 1.0.0 (main) / 1.0.0-ci.<id> (other branches)
 use   ──► consumer/                  two sources + packageSourceMapping: Contoso.* only from the feed, * from nuget.org
```

Episode 5's pipeline (GitHub Actions) and episode 6's analyzers are unchanged and not repeated. The pipeline here is **Azure
Pipelines** on purpose: Azure Artifacts and its credential flow are the part of package management that needs a service.

| Path | What it is |
|---|---|
| [`src/orders-app/Directory.Packages.props`](src/orders-app/Directory.Packages.props) | Central versions (`ManagePackageVersionsCentrally`), `CentralPackageTransitivePinningEnabled`, `CentralPackageVersionOverrideEnabled=false` |
| [`src/orders-app/Directory.Build.props`](src/orders-app/Directory.Build.props) | Episode 5 and 6 properties plus `NuGetAudit*` and the `AuditPipeline` condition (audit codes NU1900-NU1905 are errors only in the audit job) |
| [`src/orders-app/nuget.config`](src/orders-app/nuget.config) | `<clear />`, nuget.org, a mapping (`*`), `auditSources`, repository-local `globalPackagesFolder` (`.nuget/packages`) |
| [`src/orders-app/src/Contoso.Orders.Contracts/`](src/orders-app/src/Contoso.Orders.Contracts/) | The new packable library: `NewOrder`, `Page<T>`, `Paging`, `OrderRules.Validate` (moved out of the API, which now references it) |
| [`src/orders-app/azure-pipelines.yml`](src/orders-app/azure-pipelines.yml) | Two jobs: `build` (restore `--locked-mode`, build, test, `pkg_audit`, pack, `NuGetAuthenticate@1`, `dotnet nuget push --skip-duplicate`) and `audit` (`dotnet restore -p:AuditPipeline=true`, hashed Python install, `pip-audit`); weekly schedule |
| [`src/orders-app/tools/pkg_audit.py`](src/orders-app/tools/pkg_audit.py) | Reads `dotnet package list --vulnerable/--outdated/--deprecated --format json`: findings with severity, direct or transitive, the `dotnet nuget why` hint, exit code by threshold, `text`, `markdown` and `azure` output |
| [`src/orders-app/tools/requirements.in`](src/orders-app/tools/requirements.in), [`.txt`](src/orders-app/tools/requirements.txt) | The Python tools, and the `pip-compile --generate-hashes` result (every file has its sha256) |
| [`src/orders-app/tests/`](src/orders-app/tests/) | Episode 6's tests plus `OrderRulesTests.cs`; 27 pass, 4 skipped |
| [`src/consumer/`](src/consumer/) | A second repository: `OrdersReport` (a console tool that checks a CSV with the package's rules), `nuget.config` with two sources and the mapping, central versions, lock file setting. `ORGANIZATION` and `PROJECT` in the feed URL are replaced when the demo is set up |
| [`tests/fixtures/`](tests/fixtures/) | Four real `dotnet package list --format json` reports (vulnerable transitive, clean, outdated, deprecated) with the paths replaced |
| [`tests/`](tests/) | 64 pytest tests (below) |
| `src/orders-app/` (rest) | Episode 6's app without its CI, container and Python guard tooling. Changes: the version attributes left the project files, `Contoso.Orders.Api` references the Contracts project, the new library is in `OrdersApp.slnx`, the lock file of each project is regenerated |

## Run the tests

```bash
cd series/developer-tools/episodes/11-package-management
(cd src/orders-app && dotnet test)             # Passed!  - Failed: 0, Passed: 27, Skipped: 4, Total: 31 (the 4 need SQL Server)
(cd src/orders-app && ruff check . && ruff format --check .)     # All checks passed! / 2 files already formatted  (ruff 0.16.9)
python3 -m pytest -q tests                      # 64 passed (~8 min: real restores, builds, a vulnerable package, pip installs)
```

Needs .NET SDK 10 (`dotnet package`, `dotnet nuget why`), `pytest`, `pyyaml`, network access to nuget.org and PyPI, and optionally
`pip-compile` (pip-tools) and `script` (util-linux): their tests skip when missing. The first `dotnet restore` in the repo
downloads about 100 MB into `.nuget/packages` (the repository's own packages folder); the tests use a temporary folder instead
(`NUGET_PACKAGES` takes precedence over the config). Tests work on throwaway copies of the repository.

| Test file | What it proves |
|---|---|
| `test_central_versions.py` (9) | No project states a version (or `VersionOverride`) and every reference has a central version, none unused; the three CPM properties; lock files committed; the whole solution builds with episode 6's analyzers and **27 pass, 4 skipped**; `restore --locked-mode` passes on a clean copy and fails with **NU1004** after a central version changes without the lock file (and passes again after a normal restore); `VersionOverride` and a plain `Version` are refused (**NU1008** for the latter) |
| `test_audit.py` (20) | A **real pull request** (`dotnet new console`, `dotnet package add Microsoft.AspNet.WebApi.Client --version 5.2.9`, `dotnet sln add`): the solution builds; restore says `warning NU1903` for transitive **Newtonsoft.Json 10.0.1** (GHSA-5crp-9r3c-p9vr); with `-p:AuditPipeline=true` the same restore is `error NU1903`; without the two `WarningsNotAsErrors`/`WarningsAsErrors` lines episode 6's `TreatWarningsAsErrors` makes the warning break the normal build; `pkg_audit.py` exit codes by threshold, `azure` and `markdown` output, the pipeline's exact command (warning, exit 0); `dotnet package update --vulnerable` adds a direct reference and a central version; a hand-written central pin fixes it without touching a project; `dotnet nuget why` shows the path (only on a terminal); parser tests on the saved reports (vulnerable, clean, outdated, deprecated) |
| `test_feeds_and_mapping.py` (10) | The packed `.nupkg` (id, version, license, readme, no dependencies; `1.0.0-ci.57` with a suffix); pushing to a **folder** feed (twice is accepted, `--skip-duplicate` is "not supported for this type of push"); the shipped consumer config (two sources, `Contoso.*` to the feed, `*` to nuget.org, one `packageSource` per source); the consumer restores the package and prints `line 3 ... line 4 ... 2 invalid`; with the mapping wrong, **a same-named copy on the other source wins** (`0 invalid`); mapped to a source that doesn't have it, **NU1101**; no pattern at all, **NU1100** (`PackageSourceMapping is enabled, the following source(s) were not considered`); a package already in the global packages folder **ignores a corrected mapping**, and after clearing the folder the lock file stops the restore with **NU1403** |
| `test_pipeline.py` (17) | Triggers, schedule, `pool`, the two tasks and their documented inputs, step order, the conditions that keep authenticate and push out of pull requests; the **pack step runs for real** (main gives `1.0.0`, another branch `1.0.0-ci.58`); the push step runs with a recording `dotnet` shim and produces `--source https://pkgs.dev.azure.com/<org>/<project>/_packaging/contoso-packages/nuget/v3/index.json --api-key az --skip-duplicate`; the audit job's Python step runs for real (hashed install, `pip-audit`: "No known vulnerabilities found", ruff 0.16.9) |
| `test_pip_hashes.py` (6) | Every pin has a hash; `--require-hashes --dry-run` accepts the file; one wrong hash fails with "THESE PACKAGES DO NOT MATCH THE HASHES"; a pin without a hash fails and pip prints the hash to add; `pip-compile` reproduces the same set of packages |
| `test_script.py` (8) | `script.yaml`: header, 15 scenes, word count, 3 shorts, 4 screens, no markdown; every configuration excerpt is a real line of a real file; the tool output and error texts on screen are the ones the other tests assert |

**Not run here** (no browser, no sign-in, no cloud resources): the real Azure Artifacts feed and the real Azure Pipelines
run: the credential provider, `NuGetAuthenticate@1`, the permissions of the build identities, the 409 on a second push and
the feed UI; `dotnet nuget why` with a human terminal on Windows; NU1507 (needs two HTTP sources). See [demo.md](demo.md).
Azure Pipelines YAML schema validation was not possible (the schema download from SchemaStore returned a web page, not JSON);
the contract tests above and the documented task inputs stand in for it. The folder-feed tests prove the NuGet side;
they cannot prove the server's immutability.

## What we learned / gotchas

- **Central versions and lock files travel together.** Changing a `PackageVersion` without regenerating `packages.lock.json`
  fails `dotnet restore --locked-mode` with `NU1004 ... The packages lock file is inconsistent with the project dependencies`
  (tested). Commit both.
- **With CPM a `Version` next to a `PackageReference` is an error (NU1008)** and, with `CentralPackageVersionOverrideEnabled`
  off, so is `VersionOverride`. Floating versions in `PackageVersion` are refused too: **NU1011**; Learn explains why
  (a bad package could enter the build without a commit) and the opt-in property `CentralPackageFloatingVersionsEnabled`.
- **NuGet Audit is on by default**; for projects that target `net10.0` or higher `NuGetAuditMode` defaults to `all` (direct and
  transitive), otherwise `direct` (Learn). We set it explicitly. **It collides with episode 6**: `TreatWarningsAsErrors` turns
  NU1901-NU1904 into errors, so a new advisory breaks everybody's build (tested). The Learn pattern fixes it: the audit codes
  are `WarningsNotAsErrors` normally and `WarningsAsErrors` when `-p:AuditPipeline=true`, used by one dedicated job.
- **Transitive vulnerabilities, three fixes.** (1) A central pin: add `<PackageVersion Include="Newtonsoft.Json" Version="13.0.4" />`
  with `CentralPackageTransitivePinningEnabled`; no project changes, the package stays transitive (tested). (2)
  `dotnet package update --vulnerable` (.NET 10) updated Newtonsoft.Json to **13.0.1**, "the first version without known
  vulnerabilities", by adding a *direct* `PackageReference` to the project and a `PackageVersion`; Learn says to remove such a
  reference when the parent package is updated. (3) Update the parent. Learn warns that when you **pack** a library with
  transitive pinning, pinned packages become dependencies of your package: our `Contoso.Orders.Contracts` has no dependencies,
  and the pin is only in the repository that has the vulnerable client (tested: the package's dependency group is empty).
- **`dotnet nuget why` printed nothing when its output was redirected** (SDK 10.0.115, exit code 0). Run in a terminal (we used
  `script` to give it one) it prints the tree `Microsoft.AspNet.WebApi.Client (v5.2.9)` -> `Newtonsoft.Json (v10.0.1)`. In a pipeline,
  `pkg_audit.py` prints the command to run instead.
- **`dotnet package list --format json` omits `frameworks` for a project with no findings** (a project with nothing to report
  has only its `path`); the parser accepts that. Source mapping does not apply to `dotnet package list`/`add`: those send package
  IDs to **all** configured sources (Learn).
- **Source mapping is exact about "every package".** With a mapping, top-level **and transitive** packages must match a pattern;
  with no pattern for `Contoso.*` and no `*`, restore stops with NU1100; with `Contoso.*` pointed at the wrong source, only
  that source is asked (NU1101 when it lacks the package) or, if it has a same-named package, **that one is restored** (tested
  with two folder feeds that both hold `Contoso.Orders.Contracts 1.0.0`, one with different rules).
- **A package already in the global packages folder is never looked up again**, so a corrected mapping changes nothing
  (Learn says so; the test shows `0 invalid` before and after). Clearing the folder is not enough on its own: the lock file records the
  hash of the first copy and restore fails with **NU1403** until the lock file is deliberately deleted and regenerated. Keep
  lock files on, and give the repository its own packages folder (`nuget.config`, `.nuget/` ignored).
- **NU1507** (Central Package Management with more than one *HTTP* package source and no mapping) is documented but did **not**
  appear with two folder sources, so it is untested here; demo.md records it against the real sources.
- **Azure Artifacts facts from Learn:** 2 GiB of free storage per organization; package versions are **immutable** (a version
  can't be overwritten or reused, even after deleting); the `--api-key` value is required by the client but ignored (the credential
  provider authenticates); publishing from a pipeline needs both the *Project Collection Build Service* and the project's *Build
  Service* as **Feed Publisher (Contributor)**; `NuGetAuthenticate@1` must run before the push; a pull request build from an
  external fork can't authenticate; with upstream sources enabled you can't publish a version that already exists upstream.
  Pull request builds in **Azure Repos Git** come from a branch policy, not from `pr:` in the YAML, so the file has no `pr:`.
- **`--skip-duplicate`** treats a 409 from an HTTP(S) server as a warning (Learn); for a folder source dotnet prints
  `The option to skip duplicates is not currently supported for this type of push` (tested). The real 409 text is recorded in demo.md.
- **A newer NuGet idea we could not use:** `minPublishAgeHours` on a source (a cooling-off period before a new version is eligible
  for automatic selection) is documented for **NuGet 8.0 / .NET SDK 11 / Visual Studio 18.12 and later**; the SDK here is 10.
- **pip hashes:** `--require-hashes` turns on automatically as soon as one requirement has a hash and then every requirement needs
  one (tested: pip prints the hash to add); `pip-compile` must run on the Python version and platform you install on (the
  file was compiled with Python 3.13), otherwise markers and wheels differ.

## References
- Blog: [Package Management - Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-31-package-management-complete-guide-2025/)
- Microsoft Learn, NuGet: [Central Package Management](https://learn.microsoft.com/nuget/consume-packages/central-package-management) (rules, transitive pinning and pack, `VersionOverride`, NU1507) ·
  [Package Source Mapping](https://learn.microsoft.com/nuget/consume-packages/package-source-mapping) (patterns, precedence, transitive packages, global packages folder note, scope and limitations) ·
  [Auditing package dependencies for security vulnerabilities](https://learn.microsoft.com/nuget/concepts/auditing-packages) (`NuGetAuditMode` default for net10.0, warning codes, audit sources, the dedicated audit pipeline pattern, transitive fixes) ·
  [nuget.config reference](https://learn.microsoft.com/nuget/reference/nuget-config-file) (`globalPackagesFolder`, `auditSources`, `minPublishAgeHours`) ·
  [NU1011](https://learn.microsoft.com/nuget/reference/errors-and-warnings/nu1011) · [NU1507](https://learn.microsoft.com/nuget/reference/errors-and-warnings/nu1507) ·
  [dotnet nuget push](https://learn.microsoft.com/dotnet/core/tools/dotnet-nuget-push) (`--skip-duplicate`, folder sources)
- Microsoft Learn, Azure Artifacts and Azure Pipelines: [What is Azure Artifacts?](https://learn.microsoft.com/azure/devops/artifacts/start-using-azure-artifacts) (2 GiB free) ·
  [Publish NuGet packages (dotnet)](https://learn.microsoft.com/azure/devops/artifacts/nuget/dotnet-exe) (credential provider, `--api-key`, project-scoped feed URL) ·
  [Publish NuGet packages with Azure Pipelines](https://learn.microsoft.com/azure/devops/pipelines/artifacts/nuget) (build identities need Feed Publisher) ·
  [NuGetAuthenticate@1](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/nuget-authenticate-v1) ·
  [UseDotNet@2](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/use-dotnet-v2) (`useGlobalJson`, roll-forward) ·
  [PublishPipelineArtifact@1](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-pipeline-artifact-v1) ·
  [Manage feed permissions](https://learn.microsoft.com/azure/devops/artifacts/feeds/feed-permissions) ·
  [Upstream sources](https://learn.microsoft.com/azure/devops/artifacts/concepts/upstream-sources) ·
  [Feeds](https://learn.microsoft.com/azure/devops/artifacts/concepts/feeds) (delete, restore, permanently delete) ·
  [Logging commands](https://learn.microsoft.com/azure/devops/pipelines/scripts/logging-commands) (`task.logissue`, escaping)
- pip and pip-tools: [pip: Secure installs, hash-checking mode](https://pip.pypa.io/en/stable/topics/secure-installs/) ·
  [pip-tools: Using hashes](https://pip-tools.readthedocs.io/en/stable/#using-hashes) · [pip-audit](https://pypi.org/project/pip-audit/)
