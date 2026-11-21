# Demo shot list - DEVLADLOG Dev Tools #11, Package management

Already real (build machine, 21 Nov 2026): every excerpt and output on screen except the Azure DevOps and Windows views:
central versions with locked restore (NU1004 when they drift), the audit warning and its error form for a real vulnerable
transitive package (Newtonsoft.Json 10.0.1, GHSA-5crp-9r3c-p9vr), `tools/pkg_audit.py`, `dotnet package update --vulnerable`,
the packed `Contoso.Orders.Contracts`, source mapping against two feeds (folders), NU1403, `pip-compile` and `--require-hashes`,
the pipeline's own script steps, `dotnet test` (27 passed, 4 skipped) and `pytest` (see README).
**Recorded here for the first time:** the real Azure Artifacts feed and the Azure Pipelines run (sign-in through the credential
provider, `NuGetAuthenticate@1`, the 409 on a second push, the feed UI), `dotnet nuget why` in a terminal, NU1507 with two real HTTP
sources, and VS Code on Windows.
Status: **needs the recording laptop and the lab Azure DevOps organization. No Microsoft 365 tenant, no Azure subscription resource.**

## Lab environment

| What | Details | Cost |
|---|---|---|
| Azure DevOps | The lab organization (free Microsoft-hosted parallel job, 1,800 minutes a month, see `series/LAB.md`). One **private** project `contoso-packages-demo`, created and deleted in this episode. Inside it: an Azure Repos Git repository `orders-app`, an **Azure Artifacts feed `contoso-packages`** (scope: **Project**, **upstream sources not enabled**: the consumer repo uses nuget.org as its second source on purpose) and the pipeline `orders-contracts`. | none: Azure Artifacts has 2 GiB of free storage per organization (Learn); the package is about 14 KB |
| Recording laptop (Windows 11, x64) | VS Code with the C# Dev Kit or C# extension, Windows Terminal (PowerShell 7) · **.NET SDK 10** (`global.json` asks for 10.0.100 and rolls forward) · **git** · **Python 3.10 or newer** (`python`, for `tools/pkg_audit.py`) · the **Azure Artifacts Credential Provider**: `dotnet tool install --global Microsoft.Artifacts.CredentialProvider.NuGet.Tool` (run it from a folder without the repo's `nuget.config`, or add `--source https://api.nuget.org/v3/index.json`; Learn) | none |
| Accounts | `labadmin` (lab Global Administrator, the recording account) signs in to Azure DevOps and, for `dotnet restore --interactive`, through the credential provider's browser or device flow. No personal access token is created. | none |

The recording account needs **Basic** access in the organization and the **Feed Owner** role on the feed (the creator has it).
Nothing in the repo contains the organization name: `ORGANIZATION` and `PROJECT` are replaced on the laptop only. **Mask the
organization name** in every capture: the browser address bar, `pkgs.dev.azure.com/...` URLs in the terminal and the account menu.

## Setup (off camera, in this order)

1. Azure DevOps (browser): **New project** `contoso-packages-demo`, visibility **Private**, version control **Git**.
2. **Artifacts -> Create Feed**: name `contoso-packages`, visibility *Members of ...* (the project), scope **Project**, leave
   **Include packages from common public sources** unchecked. Then the gear icon (**Feed settings**) -> **Permissions** -> **Add
   users/groups**: add both **Project Collection Build Service** and **contoso-packages-demo Build Service** with the **Feed Publisher
   (Contributor)** role (Learn: both identities are needed to publish from a pipeline). If a later push fails with 403, this is the cause.
3. Put the repository in Azure Repos (PowerShell; `$mg` is the episode folder in the mg-lab checkout):

```powershell
$mg = "<path-to>\mg-lab\series\developer-tools\episodes\11-package-management"
git clone "https://<organization>@dev.azure.com/<organization>/contoso-packages-demo/_git/orders-app" orders-app   # empty repo
cd orders-app
robocopy "$mg\src\orders-app" . /E /XD bin obj .nuget .venv /NFL /NDL /NJH /NJS
git add -A; git commit -m "chore: import orders api"; git push -u origin main
```

   (`<organization>` is typed on the laptop and never appears in a capture.) Check that the three `packages.lock.json` files and
   `azure-pipelines.yml` were copied.
4. **Pipelines -> Create pipeline -> Azure Repos Git -> orders-app -> Existing Azure Pipelines YAML file** -> `/azure-pipelines.yml`;
   name it `orders-contracts`. The first run needs permission for the feed (**Permit** if asked). Expected: both jobs green,
   `Contoso.Orders.Contracts 1.0.0` in the feed. Note the run time of the two jobs. (This is the warm-up, not recorded.)
5. The consumer repository, on the laptop only (a plain folder, no Git needed):

```powershell
Copy-Item -Recurse "$mg\src\consumer" .\orders-report
cd orders-report
(Get-Content nuget.config) -replace 'ORGANIZATION','<organization>' -replace 'PROJECT','contoso-packages-demo' | Set-Content nuget.config
dotnet restore --interactive          # first time: sign in as labadmin; then the package is restored from the feed
```

   Keep `nuget.config` with the real organization **out of every capture** (use the `<organization>` placeholder copy on screen or crop).
6. Prepare the branch of the first screen, **in the Azure Repos clone**, but do not push yet:

```powershell
cd ..\orders-app
git switch -c feat/legacy-client
dotnet new console -o src/Contoso.Orders.LegacyClient --no-restore
dotnet package add Microsoft.AspNet.WebApi.Client --version 5.2.9 --project src/Contoso.Orders.LegacyClient
dotnet sln OrdersApp.slnx add src/Contoso.Orders.LegacyClient
dotnet restore       # writes src/Contoso.Orders.LegacyClient/packages.lock.json
```

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `audit` | `screens/audit.jpg` | Windows Terminal beside VS Code (`Directory.Packages.props` open). 1) `dotnet restore src/Contoso.Orders.LegacyClient --force`: `warning NU1903: Package 'Newtonsoft.Json' 10.0.1 has a known high severity vulnerability, https://github.com/advisories/GHSA-5crp-9r3c-p9vr`. 2) `dotnet restore src/Contoso.Orders.LegacyClient --force -p:AuditPipeline=true`: `error NU1903: Warning As Error: ...`. 3) `dotnet nuget why src/Contoso.Orders.LegacyClient Newtonsoft.Json`: the tree `Microsoft.AspNet.WebApi.Client (v5.2.9)` -> `Newtonsoft.Json (v10.0.1)` (it prints only in a terminal, not when redirected). 4) `python tools/pkg_audit.py --project src/Contoso.Orders.LegacyClient`: `HIGH  Newtonsoft.Json 10.0.1 ... transitive`. Three captures stitched is fine. Nobody's `.csproj` mentions Newtonsoft.Json: show that. |
| `auditjob` | `screens/auditjob.jpg` | `git add -A; git commit -m "feat(orders): add legacy client"; git push -u origin feat/legacy-client`, then **Run pipeline** on that branch (Azure Repos only triggers `main` by itself). 1) The run summary: **build** job green with a warning (the `Package audit` step annotated `Newtonsoft.Json 10.0.1 has a known high severity vulnerability`), **audit** job red: the `Restore with audit as errors` step with `error NU1903`. Note the package pushed from the branch is `1.0.0-ci.<build id>`, a pre-release (see `publish`). 2) Then in the clone: `Directory.Packages.props` gets the pin (below), `dotnet restore` (regenerates the lock files), commit, push, run again: both jobs green. |
| `consume` | `screens/consume.jpg` | In `orders-report` (placeholder copy of `nuget.config` visible): `dotnet restore --interactive` and, with detailed verbosity or `dotnet run`, the log line that installs `Contoso.Orders.Contracts` from `contoso-packages` (`dotnet restore -v n` prints `GET https://pkgs.dev.azure.com/...` for the feed: mask the organization). `dotnet run --project OrdersReport -- sample-orders.csv`: `line 3: total: total must be greater than zero`, `line 4: customer: customer is required (max 100 characters)`, `2 invalid`. Then change `Contoso.*` to `Fabrikam.*` in the mapping, `dotnet restore --force`: `error NU1101: Unable to find package Contoso.Orders.Contracts. No packages exist with this id in source(s): nuget.org`. Revert. |
| `publish` | `screens/publish.jpg` | 1) The `main` run's `Authenticate to Azure Artifacts` and `Push to the feed` steps (expand `Push to the feed`: `Pushing Contoso.Orders.Contracts.1.0.0.nupkg to 'https://pkgs.dev.azure.com/...` - mask - and `Your package was pushed.`). 2) **Artifacts -> contoso-packages**: `Contoso.Orders.Contracts` with versions `1.0.0` and `1.0.0-ci.<id>`. 3) **Re-run** the `main` run (Rerun failed jobs is not enough: use **Run new** on `main` with no new commit): the push step ends with a warning for the existing version (`409 (Conflict ...)` text) and the job succeeds. Capture the exact text for the edit. |

## Checks to make during recording (fix the README and the script if any differs)
1. **The 409.** Learn documents `--skip-duplicate` for HTTP(S) sources and says published versions are immutable; the exact warning
   text is not in the repo (the folder-feed test can't show it). Capture it. Without `--skip-duplicate` the same re-run must fail:
   try it once off camera (remove the flag on a branch) and note the message.
2. **Permissions.** If `Push to the feed` fails with 403, the two build identities need **Feed Publisher (Contributor)** on the feed (Learn).
3. **NU1507.** Remove the `packageSourceMapping` section from the consumer's `nuget.config` and `dotnet restore`: Learn says NU1507
   appears with more than one HTTP source under Central Package Management. It does **not** appear with folder sources (tested), so
   this is the first real observation. Put the section back.
4. **The credential provider flow.** Note what `dotnet restore --interactive` shows (browser, device code) and whether a second restore
   needs no prompt (Learn: the session token is cached).
5. **`dotnet package update --vulnerable`** on the `feat/legacy-client` branch (before the manual pin) should print
   `Updating Newtonsoft.Json 10.0.1 to 13.0.1` and add a `PackageReference` to the legacy client project (tested on Linux). Optional
   capture; the script scene shows the manual pin.
6. **Nothing is cached by accident.** The repo stores packages in `.nuget/packages` (`nuget.config`), so the first restore downloads
   about 100 MB of Entity Framework Core and SQL client packages. Run it once before recording.

The pin for step 2 of `auditjob` (add to `Directory.Packages.props`, before the `Tests` item group):

```xml
  <ItemGroup Label="Pinned transitive packages">
    <PackageVersion Include="Newtonsoft.Json" Version="13.0.4" />
  </ItemGroup>
```

## Tear-down
1. Delete the **feed**: Artifacts -> `contoso-packages` -> Feed settings -> **Delete feed** (Feed Owner). Learn: a deleted feed stays 30
   days in **Deleted Feeds** and still uses storage; open that tab, select the feed -> Feed settings -> **Permanently Delete Feed**.
2. **Project settings -> Overview -> Delete** for `contoso-packages-demo` (removes the repo and the pipeline).
3. Laptop: delete the `orders-app` and `orders-report` folders, run `dotnet nuget locals all --clear`, and
   `dotnet tool uninstall --global Microsoft.Artifacts.CredentialProvider.NuGet.Tool` if it was installed for this episode.
4. Check **Organization settings -> Billing / Artifacts storage** the next day: it should be back at 0 GiB (Learn: storage figures can
   take up to 48 hours to refresh).
