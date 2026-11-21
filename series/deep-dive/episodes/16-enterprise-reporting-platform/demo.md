# Demo shot list — DEVLADLOG Deep Dive #16, Enterprise Reporting Platform

Code and test scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Fabric trial capacity (+ episode 15 deployed for real data).** Offline (container, no tenant): 23 xUnit tests
(`dotnet test`) and 23 Pester tests pass. **Not yet run against Power BI / Fabric:** opening and publishing the model, the role and
`Invoke-RlsCheck`, the deployment pipeline and its REST call, the scanner API, endorsement. Record the outcome of each in the README
("Not verified in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge (Power BI service / Fabric portal, Azure portal), **Power BI Desktop**, VS Code with the
TMDL extension, Windows Terminal with PowerShell 7 and the .NET 8 SDK. No Hyper-V VM and no Azure resource of its own: this episode adds **no
resource group**. Nothing from `series/LAB.md` is consumed except the tenant, the **Fabric + Power BI 60-day trial** (West Europe capacity)
and the lab users. No IP is used on 10.50.0.0/24.

**Data source:** the Synapse serverless database `contoso_analytics` from episode 15 (its resource group `rg-mglab-deep-dive-15`, West Europe, cost
and tear-down are in that episode's `demo.md`). If episode 15 was already torn down, redeploy it first, or record with the sample data stated on screen.
Check that the Fabric trial is still running (OneLake catalog > Govern > Capacities > Trial): it lasts 60 days (Learn). Cost of this episode: **0 EUR**
(trial capacity; Power BI Desktop is free); the Azure cost is the episode 15 one.

**Capacity size matters.** Learn: the trial is an F4 or an F64. Free-licence viewers can view Power BI content only on F64 or larger (or Premium).
The lab users all have E5 licences, which include Power BI Pro in the usual E5 bundle: check each user's licence in the Microsoft 365 admin center and
write it in the README; do not demonstrate a "free viewer" unless the capacity is F64.

**Microsoft Entra / Power BI users (existing lab users, nothing to create):**

| User | Role in this episode | Sees |
|---|---|---|
| `labadmin` | Fabric admin, workspace **Admin**, pipeline admin. Bypasses RLS: never used to prove RLS | everything |
| `alex.demo` | workspace **Viewer**, role member | Finance (FIN) |
| `sam.demo` | workspace **Viewer**, role member | Operations (OPS) |
| `jordan.demo` | workspace **Viewer**, role member | Information Technology (IT) |
| `riley.demo` | workspace **Viewer**, role member | Human Resources and Marketing (HR, MKT) |
| `taylor.demo` | certifier: member of the security group `sg-mglab-certifiers` (created in setup) | n/a |

All users get `@<lab domain>`; the domain is typed into the `UpnDomain` parameter, never committed. Departments are not set on the lab
users and this episode does not need them: the mapping is the `SecurityMap` table.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/16-enterprise-reporting-platform
   dotnet test test/ModelTests/ModelTests.csproj -m:1        # expect Passed: 23
   pwsh -NoProfile -c 'Invoke-Pester ./tests'                # expect Tests Passed: 23
   ```
2. **Workspaces on the trial capacity** (as `labadmin`): create three workspaces `Contoso Reporting [DEV]`, `[TEST]` and `[PROD]` and assign them to the
   Fabric trial capacity. Add `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo` as **Viewer** to `[PROD]` and `[TEST]` only. Do not make them Member or Contributor anywhere.
3. **Get the model into `[DEV]`.** Not verified: this path was not run.
   a. In Power BI Desktop create a blank report and save it as a Power BI project (File > Save as, `.pbip`, TMDL format; Learn: project semantic model folder).
   b. Close Desktop. Replace the project's `<name>.SemanticModel/definition` folder with `model/ContosoReporting.SemanticModel/definition` (keep the generated `.platform` and `definition.pbism`; ours is version 4.0).
   c. Reopen the `.pbip`. Set the parameters (Transform data > Manage parameters): `SynapseServer` = the `-ondemand` endpoint, `SynapseDatabase` = `contoso_analytics`, `UpnDomain` = the lab domain. Sign in with the organisational account when asked, **Refresh**.
   d. Build the report on camera or off camera: a card per measure, `Avg Cycle Days` by `DimDepartment[DepartmentName]`, `Amount YTD` by `DimDate[Month]`. Publish to `[DEV]`. If any TMDL error appears, fix the file and rerun `dotnet test`.
4. **Pipeline:** Fabric portal > Deployment pipelines > create `Contoso reporting` with three stages, assign `[DEV]`, `[TEST]`, `[PROD]`.
5. **Certification group** (Entra): create `sg-mglab-certifiers` with `taylor.demo`. A Fabric admin (`labadmin`) enables **Certification** in tenant settings for that group. Put `taylor.demo@<domain>` in `governance/policy.json` `certifiers` for the recording (undo in tear-down).
6. **Scanner API:** a Fabric admin must enable the metadata scanning tenant settings (Learn: scanner API). Not verified: the exact settings.
7. **Tokens** (never printed, never written to a file): `$token = az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv` signed in as the **non-admin** viewer for `Invoke-RlsCheck`; the Fabric token for `Invoke-PipelineDeploy` uses the resource `https://api.fabric.microsoft.com`. `az login` happens off camera. Not verified: that these tokens carry the needed scopes (Learn: `Dataset.Read.All`, `Pipeline.Deploy`).

## Screens to capture

Capture order = script order. Every screen shows the real service. Mask the endpoint, workspace and tenant names.

| Scene | What must be on screen | Steps |
|---|---|---|
| `model-screen` | VS Code on `FactPurchaseRequest.tmdl`, then Power BI Desktop with the project open and the TMDL view showing the same measure | Parameters set off camera; blur the server name |
| `rls-screen` | Power BI service: semantic model > Security > role `Department Reader` with the four members; Test as role as `alex.demo` showing only Finance; then the terminal with `Invoke-RlsCheck` output | `Import-Module ./scripts/ReportingGovernance.psm1`; `Invoke-RlsCheck -DatasetId <id> -MapCsv governance/fixtures/security-map.csv -CountsCsv governance/fixtures/requests-by-department.csv -AccessToken $token`. Update the counts CSV from `SELECT DepartmentKey, COUNT(*) FROM gold.FactPurchaseRequest GROUP BY DepartmentKey` first. Show once that a workspace Admin sees all rows |
| `pipeline-screen` | Deployment pipeline with three stages; Compare DEV and TEST; Deploy with a note; Deployment rules on TEST for `SynapseServer`; deployment history | Create the parameter rule on the TEST stage, deploy again so the rule applies (Learn: rules apply on deployment). Then add the role members in TEST again: they are not copied |
| `governance-screen` | Scanner run for the three workspaces and `Get-GovernanceFindings` output; the semantic model's Endorsement settings: Promoted by `labadmin`, Certified by `taylor.demo` | `New-ScanRequest -WorkspaceId ...` gives the getInfo body; POST it, poll `scanStatus`, GET `scanResult`, save as `scan.json` (do not commit); `Get-GovernanceFindings -ScanResultPath scan.json -PolicyPath governance/policy.json` |

State once on screen that the data is synthetic (episode 15).

## Tear-down

1. Delete the three workspaces `Contoso Reporting [DEV|TEST|PROD]` and the deployment pipeline `Contoso reporting`.
2. Remove the security group `sg-mglab-certifiers`; revert the Certification tenant setting and the scanner tenant settings if the admin changed them for the recording.
3. Restore `governance/policy.json` (`git checkout`), delete `scan.json`, any saved `.pbip` project (it holds the endpoint name) and the Power BI Desktop data source credentials (File > Options and settings > Data source settings).
4. The Fabric trial capacity stays (shared); tear down episode 15 per its own `demo.md` if finished with it.
