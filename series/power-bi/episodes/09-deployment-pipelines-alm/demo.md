# Demo shot list — Power BI #9 Deployment Pipelines & ALM

## Lab environment

Tenant work is real: the Power BI service on the lab tenant, a Fabric trial capacity, and Power BI Desktop on the Windows
laptop (`series/LAB.md`). **No gateway is needed**: the lab has no on-premises data gateway yet (episode 14), so the model
reads CSV exports from a SharePoint document library, which the service reaches directly. CON-SQL01 (10.50.0.30) and the
Hyper-V network 10.50.0.0/24 are not used in this episode. No Azure resource is created, so there is no resource group
`rg-mglab-powerbi-09` to tear down.

| What | Details | Cost |
|---|---|---|
| Fabric trial capacity | assigned to the three workspaces below (a pipeline needs a Fabric capacity workspace) | free (trial) |
| Workspaces | `Contoso Sales (Lab) - Dev`, `Contoso Sales (Lab) - Test`, `Contoso Sales (Lab) - Prod`; Test and Prod stay empty until the first deployment | free |
| Deployment pipeline | `Contoso Sales (Lab)`, the default three stages, Development / Test / Production | free |
| SharePoint | a site `Contoso Bikes Data` on the lab tenant with two library folders: `exports` (24 files, `src/data/ContosoBikesData/exports`) and `exports-sample` (3 files, `exports-sample`) | free |
| Users | `alex.demo` (pipeline admin, admin of the three workspaces and owner of the SharePoint site); the other lab users are not needed | — |
| Recording laptop | Power BI Desktop (current release), PowerShell 7.2+, Python 3.10+ | free |

## What was verified where

| Step | Verified in the container | Needs tenant / Desktop (recording day) |
|---|---|---|
| Model, parameters, partition M | TMDL loaded by the Tabular Object Model, M parsed by Microsoft's Power Query parser, Python mirror of the M gives the expected values | **the first refresh of the M against SharePoint**, and that Desktop opens the `.pbip` (needs Desktop) |
| Report | PBIR schemas, layout spec | whether Desktop opens it (needs Desktop) |
| Pipeline, rules, deployment, refresh | — | **all of it** (needs tenant) |
| REST calls (Get Pipelines, stages, artifacts, Selective Deploy, Deploy All, operations) | Pester tests against mocks shaped like the samples on Learn | **real responses**: property names (`artifactName` / `artifactDisplayName`) and status values (needs tenant) |
| Pre-deploy rules AL001-AL012, PD001-PD005 | pytest and Pester with synthetic fixtures | — |
| Learn's PBIR limitation vs PBIR default (rule AL007) | — | **deploy the report and write down what happens** (needs tenant) |

## Setup (off camera, once)

1. Tenant (needs tenant): create the three workspaces on the trial capacity. Create the pipeline `Contoso Sales (Lab)` from
   the Development workspace, and assign `- Test` and `- Prod` to the other two stages.
2. SharePoint (needs tenant): upload the two folders to a library. In Desktop open `src\ContosoSales.pbip`, **Transform data >
   Edit parameters**: `ExportSite` = the lab site address. Refresh, check the cards (Dev values below), **Publish** to
   `Contoso Sales (Lab) - Dev`. Set the SharePoint credentials of the Dev model (organizational account, `alex.demo`).
3. Expected card values (computed by `src/tools/expected.py`; confirm they match the real cards):

   | Stage | Stage card | Sales Amount | Orders | Order Lines |
   |---|---|---|---|---|
   | Development (`exports-sample`, 3 files) | DEV | 220,652.08 | 283 | 478 |
   | Test and Production (`exports`, 24 files) | TEST / PROD | 1,862,401.98 | 2,440 | 4,071 |

4. In a PowerShell 7 terminal, `Connect-PowerBIServiceAccount` as `alex.demo` (needs tenant; this is a sign-in done by the
   person recording, never by the build).
5. Rehearse with `-WhatIf`: `.\src\pipeline\Invoke-PipelineRelease.ps1 -PipelineName 'Contoso Sales (Lab)' -From 0 -Note 'Release 1' -WhatIf`.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen (needs tenant unless stated) |
|---|---|---|
| `pipeline` | `screens/pipeline-stages.jpg` | Power BI service > **Deployment pipelines** > `Contoso Sales (Lab)`: the three stage cards with their workspace names. Development lists the semantic model and the report; Test and Production are empty. Mask the capacity name if it shows a tenant name. |
| `rules` | `screens/rules.jpg` | Test stage > **Deployment rules** > `ContosoSales` > **Parameter rules**: `ExportsFolder` = `exports`, `StageName` = `TEST`. Repeat in Production (`PROD`). Show that the Development stage has no deployment rules option. The values are printed by `python src/tools/alm_check.py rules --model src/ContosoSales.SemanticModel/definition --stages src/pipeline/stages.json`. |
| `deploy` | `screens/deploy.jpg` | Development stage selected: the compare shows the model and report as new. **Deploy to test**, a note, then the finished deployment. Open the Test report before the refresh: it has no data (record exactly what is shown). |
| `stages` | `screens/three-stages.jpg` | After the first refresh in Test and Prod (sign in to the SharePoint source of each model first): the report's cards in Dev, Test, Prod, the same page each time. Values in the table above; record the real ones. |

## Not a screen scene, but record it

- `Invoke-PipelineRelease.ps1 ... -From 1` (Test to Production): the console shows the paired items, the PD checks, the
  deployment status and the refresh start. Record the property names and the status string of the real operation.
- The PBIR question: if the deployment of the report fails or the report is not deployed, say so on camera and keep the
  message. If it deploys, say that too. Learn lists "PBIR reports aren't supported" as a limitation and calls PBIR the default.
- A service principal is not used (it can't configure OAuth credentials). Everything runs as `alex.demo`.

## Masking

- Mask the tenant name, the capacity name, the SharePoint site address and any e-mail address except `alex.demo`.
- Workspace and pipeline ids in the address bar: crop the browser or blur them.
- Do not show the token of `Connect-PowerBIServiceAccount`, and clear the terminal history afterwards.

## Tear-down

1. Delete the pipeline (**Pipeline settings**), then the three workspaces.
2. Delete the SharePoint site folders `exports` and `exports-sample` (or the site).
3. `Disconnect-PowerBIServiceAccount`. End the Fabric trial only if it is not used by the next episode.
4. Nothing to delete in Azure for this episode.
