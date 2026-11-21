# DEVLADLOG Power Apps #9 — ALM and DevOps for Power Platform: from DEV to PROD without clicking in PROD

Until now every Equipment Desk change happened in one environment, by hand. This episode moves the **Equipment Desk solution**
through three environments (DEV, TEST, PROD) with source control and two Azure Pipelines that use **Power Platform Build Tools**:

- **Export pipeline** (manual): export the solution twice (unmanaged and managed), unpack both into an empty folder,
  mirror that folder into the repo, lint it, push an `export/<run>` branch for a pull request. Nothing is committed to `main`.
- **Build and release pipeline** (on `main`): lint the source, stamp the version from the run number, pack an unmanaged and a managed
  zip, run the **solution checker**, publish an artifact; then import the **managed** zip into **TEST**, and into **PROD** after an
  approval on the PROD environment. Environment-specific values come from a deployment settings file, never from the solution.
- Episode 6 had a hard-coded `@contoso.com` in the reminder flow (and a demo note about changing it off camera). The solution now
  carries an **environment variable**, `contoso_ReminderDomain`, with a different value in TEST and PROD, and two **connection
  references** (`contoso_EquipmentDeskDataverse`, `contoso_EquipmentDeskOutlook`) that each environment binds to its own connection.

Why scripts around the Build Tools tasks? Because the mistakes that hurt show up late: a source that can't be packed as managed, a
file left behind by an unpack, a connection id in git, a version nobody stamped. Each of these is a script that runs in the pipeline and
a test that proves it fails when it should.

| Path | What it is |
|---|---|
| [`src/solution/EquipmentDesk`](src/solution/EquipmentDesk) | The solution source, in the layout `pac solution unpack --packagetype Both` writes: `Other/Solution.xml` (publisher `contoso`, version, `Managed` 2), `Other/Customizations.xml` (two connection references), `environmentvariabledefinitions/contoso_ReminderDomain` |
| [`src/pipelines/export-solution-to-git.yml`](src/pipelines/export-solution-to-git.yml) | Export (unmanaged + managed) → unpack as Both into a temp folder → `Sync-SolutionSource.ps1` → push branch |
| [`src/pipelines/build-and-release.yml`](src/pipelines/build-and-release.yml) | Stages **Build** (lint, version, pack, checker, artifact), **Test**, **Prod** (deployment jobs on environments `equipmentdesk-test` / `equipmentdesk-prod`) |
| [`src/pipelines/templates/deploy-managed.yml`](src/pipelines/templates/deploy-managed.yml) | The steps both deploy stages share: find the managed zip, fill the settings, WhoAmI, import (holding solution), apply upgrade |
| [`src/settings/test.settings.json`](src/settings/test.settings.json), [`prod.settings.json`](src/settings/prod.settings.json) | Deployment settings templates in Learn's format: configuration values written out, connection ids as `${TOKENS}` |
| [`src/scripts/Test-SolutionSource.ps1`](src/scripts/Test-SolutionSource.ps1) | Gate S01-S11 on the unpacked folder (names, version, `Managed`, prefix, env var rules, no connection ids, no environment URLs) |
| [`src/scripts/Set-SolutionVersion.ps1`](src/scripts/Set-SolutionVersion.ps1) | `pac solution version` for build and revision (two calls, see gotchas) |
| [`src/scripts/Invoke-SolutionPack.ps1`](src/scripts/Invoke-SolutionPack.ps1) | `pac solution pack --packagetype Both`, names the zips after the version, opens both and checks `Managed` 0/1 and the version |
| [`src/scripts/Sync-SolutionSource.ps1`](src/scripts/Sync-SolutionSource.ps1) | Mirrors a fresh unpack into the repo folder (deleting what's gone), prints added/changed/removed, runs the gate |
| [`src/scripts/Resolve-DeploymentSettings.ps1`](src/scripts/Resolve-DeploymentSettings.ps1) | Fills `${TOKENS}` from environment variables, checks the file against the solution (nothing missing, nothing unknown, same connector ids), writes the file the import task reads |
| [`src/scripts/Get-Package.ps1`](src/scripts/Get-Package.ps1) | Finds the one `*_managed.zip` in the artifact and sets a pipeline variable |
| [`tests/`](tests) | 84 pytest tests: real `pac` offline, the scripts, the settings, and a pipeline linter built from Learn's task reference |
| [`tests/fixtures/build-tools-tasks.json`](tests/fixtures/build-tools-tasks.json) | Task ids and input names copied from Learn's Build Tools tasks page (21 Nov 2026), used by the linter |

## Run the tests (no tenant needed)

Needs `pac` (Power Platform CLI 2.16.1 here), PowerShell 7 (with PSScriptAnalyzer) and Python 3 with `pytest` and `PyYAML`. About four minutes
(most of it is PowerShell starting up).

```bash
cd tests
python3 -m pytest -q
# 84 passed in 230s   (pac 2.16.1, PowerShell 7.6, Python 3.13, pytest 9.1)
```

What the groups prove:
- **test_source_lint** (17): the committed source passes S01-S11; each rule fails when its mistake is made (wrong name, version, `Managed` 0,
  prefix, dangling root component, folder/schema name mismatch, committed env var values file, Secret with a default, connection id in a
  reference, connector id without `/providers/...`, environment URL, tenant name); broken or missing XML is reported, several mistakes at once.
- **test_pack** (15), all with the real `pac`, offline: pack Both writes `EquipmentDesk_1_0_0_0.zip` and `..._managed.zip` with `Managed` 0 and 1
  and the env var definition inside; **pack then unpack as Both gives back byte-identical source**; a source unpacked as unmanaged can't be
  packed as managed; unpack leaves files of removed components behind; `Sync-SolutionSource` removes them, reports added/changed/removed, refuses a
  folder that isn't a solution; `Set-SolutionVersion` stamps `1.0.20261121.3` and the zips carry it; `pac solution create-settings` finds the
  env var and both connection references; `Get-Package` takes exactly one managed zip.
- **test_settings** (17): both templates resolve into the documented format; the log names the tokens and never prints values; missing variables
  are all listed and nothing is written; a template that misses or invents an env var or connection reference, has another connector id,
  or an empty value is refused; no connection id, GUID, environment URL or tenant name is committed anywhere in `src`.
- **test_pipelines** (33): both YAML files pass the linter (task ids and inputs exist on Learn, tool installer first, scripts exist,
  Build to Test to Prod, deployment jobs on environments, only `mglab-<target>` service connections, only the managed zip is imported,
  settings file matches the resolve step, checker on the managed zip, unpack as Both into a temp folder, push only to an `export/` branch) and **each
  rule fails on a mutated copy** (28 mutations, plus one test for `pac` before the installer).
- **test_scripts_quality** (2): all scripts parse and pass PSScriptAnalyzer (errors and warnings).

What they **don't** prove: that Azure Pipelines accepts the YAML (the linter is ours, not the service's), that the Build Tools tasks behave as
Learn says against a real environment, that the hand-written source imports (it's a skeleton with the same layout `pac unpack` writes; it has no
tables, app or flow), the service connections, approvals, the solution checker, the import and upgrade, the connections. That's the lab run in
[`demo.md`](demo.md). Everything the `pac` tests rely on was observed with 2.16.1; a newer `pac` may change the messages two tests look for.

## Build it in the lab (needs tenant)
TEST and PROD environments, a service principal per environment (`pac admin create-service-principal`), the Power Platform Build Tools
extension in the Azure DevOps organization, three service connections, two variable groups, two environments (approval on PROD), the repo
with the contents of `src`, then: run the export pipeline in DEV, merge the PR, watch Build → Test → (approve) → Prod. `demo.md` has every step and what
it costs. This has **not yet run against the lab tenant**.

## What we learned / gotchas

- **A source unpacked as unmanaged can't be packed as managed.** `pac solution pack --packagetype Managed` on a folder whose `Solution.xml` says
  `<Managed>0</Managed>` stops with "Solution package type did not match requested type" (observed, pac 2.16.1). Learn's SolutionPackager article
  has the way out: export **twice** (`Name.zip` and `Name_managed.zip`, same folder) and unpack with `PackageType` **Both**; `Solution.xml` then says
  `Managed` 2 (we saw it) and one folder packs both. Learn's Unpack task lists Unmanaged as the recommended type, so don't copy that blindly if the build
  has to produce a managed zip.
- **`pac solution unpack` doesn't delete.** It prints "Not deleting files" and the folder of a removed component stays, so the next pack puts it back
  (`--allowDelete` defaults to false). The pipeline unpacks into an empty temp folder and `Sync-SolutionSource.ps1` mirrors it, so `git diff` shows removals.
- **`pac solution version` takes the build and the revision in separate calls.** Both in one call gives "Must provide either --buildversion or
  --revisionversion or --strategy" (observed). `Set-SolutionVersion.ps1` calls it twice. major.minor are changed by people.
- **Definitions in the solution, values in the target.** Learn's environment variables FAQ: "Environment variable definitions should be included in
  your solution but the values should be provided for the target environment during deployment" and values are separate JSON files in the exported zip;
  remove the current value from the solution before exporting (Current value → ... → Remove from this solution). Gate S08 fails if a values file is
  committed. We lint for any file named `*environmentvariablevalue*`; the exact file name `pac` writes wasn't checked, the lab run confirms it.
- **A changed value doesn't reach a flow immediately.** Learn: when values are changed in the environment and not by a solution import, flows keep the previous
  value until they're saved or turned off and on; for apps and flows it can take up to an hour to fully publish. The import path is the supported one.
- **Connection ids don't go in git.** The settings templates carry `${TEST_CONNECTION_OUTLOOK}` etc.; the variable group in Azure DevOps supplies them and
  the log shows names, never values. Learn's deployment settings format: `EnvironmentVariables` (`SchemaName`, `Value`) and `ConnectionReferences`
  (`LogicalName`, `ConnectionId`, `ConnectorId`). `pac solution create-settings` (2.16.1) writes more keys (`DefaultValue`, `Name`, `TypeId`, ...,
  `CopilotAgents`); the resolve script writes only the documented ones.
- **Who owns the connection?** Learn: the user turning a flow on must own or be allowed to use every connection in it, and "OAuth connections can
  only be explicitly shared with a user representing a service principal" (Can use). So the Outlook connection in TEST and PROD is created by a person and
  **shared with the service principal's application user**, or the import can't turn the flow on.
- **Azure Repos ignores `pr:` in YAML.** Learn: for Azure Repos Git, PR validation is a **build validation branch policy**. The release pipeline's
  Test and Prod stages skip `Build.Reason` PullRequest runs, so a validation build only packs and checks.
- **The build service needs permissions to push.** Learn (Run Git commands in pipeline scripts): the identity is `<project> Build Service (<organization>)`, not
  "Project Collection Build Service Accounts"; typical permissions **Create branch, Contribute, Read, Create tag**; `checkout` with `persistCredentials: true`.
- **Task versions can't be mixed** (Learn, Build Tools v2 is `pac`-based and runs on Linux too); the **tool installer** goes before any other Build Tools
  task, and `AddToolsToPath: true` makes `pac` available to our scripts.
- **You can't import a managed solution into the environment that has the unmanaged one** (Learn, Solution concepts): TEST and PROD must be other environments.
- **Upgrade or update?** Update can't delete components; upgrade removes what's no longer in the solution (Learn). The template imports as a **holding
  solution** and applies the upgrade. We did **not** verify what a holding import does in an environment that doesn't have the solution yet, so the
  pipeline has a parameter, `upgradeExisting` (default on); turn it off for the very first install.
- **`RootComponent type="380"` for an env var made `pac pack` say "root components are not defined in customizations".** Public exported solutions we looked
  at (PnP and Microsoft samples) list environment variables only as folders, so the skeleton does too; the zip contains the definition either way. If your
  real export lists them, keep what `pac unpack` wrote.
- **Trial environments** (Learn): "Trial (standard)" expires after 30 days, is limited to one per user and can't be copied, backed up or reset; "subscription-based"
  trials are created by tenant admins. Neither consumes paid capacity. Create TEST and PROD right before the recording.

## References
- [Microsoft Power Platform Build Tools for Azure DevOps (v2, service connections, service principal)](https://learn.microsoft.com/power-platform/alm/devops-build-tools)
- [Build Tools tasks (task ids, inputs, examples)](https://learn.microsoft.com/power-platform/alm/devops-build-tool-tasks)
- [Pre-populate connection references and environment variables (deployment settings file)](https://learn.microsoft.com/power-platform/alm/conn-ref-env-variables-build-tools)
- [Solution concepts (managed/unmanaged, update, upgrade, patch, publisher)](https://learn.microsoft.com/power-platform/alm/solution-concepts-alm)
- [SolutionPackager tool (PackageType Both, `_managed.zip` naming)](https://learn.microsoft.com/power-platform/alm/solution-packager-tool)
- [pac solution](https://learn.microsoft.com/power-platform/developer/cli/reference/solution)
- [Environment variables overview (values, FAQ, limits)](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables)
- [Environment variables in cloud flows](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables-power-automate)
- [Connection references in solutions (ownership, sharing with a service principal)](https://learn.microsoft.com/power-apps/maker/data-platform/create-connection-reference)
- [Run Git commands in pipeline scripts (build service permissions, persistCredentials)](https://learn.microsoft.com/azure/devops/pipelines/scripts/git-commands)
- [Build Azure Repos Git repositories (PR triggers are branch policies)](https://learn.microsoft.com/azure/devops/pipelines/repos/azure-repos-git)
- [About trial environments](https://learn.microsoft.com/power-platform/admin/trial-environments) and [Create and manage environments](https://learn.microsoft.com/power-platform/admin/create-environment)
- Blog: [ALM & DevOps for Power Platform — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-03-08-alm-devops-for-power-platform-complete-guide-2026/)
