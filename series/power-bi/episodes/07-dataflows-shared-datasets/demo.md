# Demo shot list — Power BI #7 Dataflows & Shared Datasets

## Lab environment

No VM and no Azure resource. Everything runs on the recording laptop and in the lab tenant (`series/LAB.md`).

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current), PowerShell 7, Windows Terminal, browser with an InPrivate window, git | free |
| PowerShell module | `MicrosoftPowerBIMgmt` (`Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser`) | free |
| Lab tenant: capacity | Fabric + Power BI 60-day trial (West Europe). Dataflow Gen2 needs a Fabric-enabled workspace on the trial capacity | trial, €0 |
| Lab tenant: workspace 1 | **Contoso Data (Lab)**: new, trial capacity, admin `labadmin`. Holds the dataflow and the shared model | €0 |
| Lab tenant: workspace 2 | **Contoso Sales (Lab)**: from episodes 5 and 6 (still has the file-based *ContosoSales* model, its report and the dashboards). Holds the thin report | €0 |
| Lab tenant: SharePoint site | **ContosoBikesData** (team site, Microsoft 365 E5 trial). Library *Documents* with folders `exports` and `security` (step 1) | €0 |
| Lab tenant: Azure DevOps | Organization from `series/LAB.md`; a private project `mglab-pbi-ep07` with one repo (deleted in tear-down). Only for Git integration (step 3) | €0 (free grant) |
| Lab users | `labadmin` (records), `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo` (Store Managers), `jordan.demo` (Head Office) | trial |
| Tenant settings (check only) | Fabric items can be created, Git integration enabled for the workspace, *Use semantic models across workspaces* on, **Publish to web stays off**. Certification is optional: this shot list *promotes* (any member with write permission can) | €0 |

Screens are recorded in the browser (lab tenant), Power BI Desktop and Windows Terminal on the laptop. Nothing is recorded from the container.

## What was verified where

| Step | Verified in the container | Needs the tenant |
|---|---|---|
| Queries: syntax, names, no local paths | Microsoft's Power Query parser + `pq-lint` (10 queries, 0 findings), Python mirror of every step | **first run of the M** (never executed outside the service) |
| Dataflow item folder (`mashup.pq`, `queryMetadata.json`, `.platform`) | generated, parsed as a section document, `.platform` validated against Microsoft's schema, fields compared with Learn | **import through Git integration** |
| Contract vs model | `check_contract.py` + mutation tests; TOM loads the model folder | refresh of the model against the real dataflow |
| Thin report folder | PBIR schemas, report lint against the model's fields | **whether Desktop opens it** (primary flow below creates it in Desktop instead) |
| `Invoke-SharedModelCheck.ps1`, `Set-PbiModelParameter` | Pester with the REST cmdlet mocked (responses shaped like the Learn samples) | **real run** |
| Publish, permissions, RLS, endorsement, lineage | — | **all of it** |

## Setup (off camera, once)

1. **SharePoint.** Create the team site *ContosoBikesData*. In *Documents* create folders `exports` and `security`; upload
   `src/data/ContosoBikesData/exports/*` (24 CSV files and `_README.txt`) and `security/store_access.csv`. Copy the site URL.
2. **Workspace.** Create *Contoso Data (Lab)* on the trial capacity. Add `jordan.demo` as Viewer only if the Head Office
   scene is recorded (optional).
3. **Dataflow from Git.** In Azure DevOps create project `mglab-pbi-ep07`, repo with one folder:
   copy `src/dataflow/ContosoBikesPrep.Dataflow/` to the repo root (a folder named `ContosoBikesPrep.Dataflow`, as
   Learn's *Git integration source code format* describes: `{display name}.{type}`), edit `ExportSite` in `mashup.pq` to
   the real site URL **in the repo copy only**, commit to `main`. In the workspace: **Workspace settings > Git integration**,
   connect to that repo and branch, **Sync**. The dataflow *Contoso Bikes Prep* appears.
   *If the import doesn't work* (this exact path is not verified): create **New item > Dataflow Gen2** by hand and, for each
   query in `mashup.pq` (order: `ExportSite`, `fnReadExport`, `fnDimension`, `SalesExport`, then the six entities),
   create a blank query and paste its body into the Advanced editor. Tell the maintainer which path worked.
4. **Connection.** Open the dataflow, **Edit**: when asked, configure the SharePoint connection (organizational account
   `labadmin`). Check, per query, what the editor shows for *Enable staging* and *Enable load* (expected: the six
   entities loaded, the four staging queries not). **Save and run** / **Publish**, then **Refresh**. Note the refresh duration.
5. **Model.** Copy `src/` to `C:\MGLab\power-bi\ep07\src` and open `ContosoSales.pbip` in Desktop. **Transform data >
   Edit parameters**: `WorkspaceId`, `DataflowId` (from the URLs of the workspace and the dataflow; never typed on camera),
   `UpnDomain` = the lab domain. Sign in to the Dataflows connector with `labadmin`. **Refresh**.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `dataflowscreen` | `screens/df-editor.jpg` | Workspace *Contoso Data (Lab)* > dataflow *Contoso Bikes Prep* > **Edit**. Queries pane showing the groups **Parameters**, **Staging**, **Output** and the 6 output queries; select `Sales` (4,071 rows in the preview if it shows a count) and open **Diagram view**. Back in the workspace: the **Refresh** that finished with its time. Mask the SharePoint URL (the `ExportSite` value). |
| `modelscreen` | `screens/df-model.jpg` | Desktop with `ContosoSales.pbip`: **Transform data**, query `Product`, the Applied steps (`Source`, `Workspaces`, `Workspace`, `Dataflow`, `Product`) and **Edit parameters** with the IDs masked. Back in the report: **Refresh** done; page *Sales overview* with the Year slicer cleared: Sales amount **1,862,401.98**, Orders **2,440**. Then **Home > Publish** > *Contoso Data (Lab)*. In the service, model **Settings**: *Parameters* (IDs masked) and **Refresh**; **Endorsement** > *Promoted*, add a description, tick *Make discoverable* if shown. |
| `thinscreen` | `screens/df-thin.jpg` | New Desktop window, **Get data > Power BI semantic models**: the OneLake catalog list with *ContosoSales* (Promoted badge, workspace *Contoso Data (Lab)*; also the older *ContosoSales* in *Contoso Sales (Lab)* if listed): **Connect**. Show the Data pane with all tables and measures and the status bar *Connected live*. Build one page (cards Sales amount, Orders, Visible stores; table of stores), save as `StoreManagers.pbip`, **Publish** > *Contoso Sales (Lab)*. In the service, **Lineage view** of *Contoso Sales (Lab)* (or the data workspace): SharePoint → dataflow → model → reports in both workspaces. **Also record** `definition.pbir` of the saved project next to `src/thin-report/StoreManagers.Report/definition.pbir` and send the diff to the maintainer. |
| `auditscreen` | `screens/df-audit.jpg` | Terminal in `C:\MGLab\power-bi\ep07\src\service`, signed in with `Connect-PowerBIServiceAccount`: `./Invoke-SharedModelCheck.ps1 -DataWorkspaceId $dataWs -ReportWorkspaceId $salesWs` (variables set off camera). Expected: the two counts lines, **SM001** (*ContosoSales* in both workspaces), **SM002** (the thin report), possibly **SM003** (the REST links may not list a Gen2 dataflow: record exactly what appears and fix the narration of `auditscreen` to match), exit code. |
| `rlsscreen` | `screens/df-rls.jpg` | Model *ContosoSales* in *Contoso Data (Lab)* > **Security**: add `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo` to *Store Managers* (`jordan.demo` to *Head Office*). **Manage permissions** > add the same users with **Build** (read the dialog: record its wording). Open the thin report as `sam.demo` in an **InPrivate** window (Apps, or the workspace link): *Signed in as* shows Sam Demo, *Visible stores* **1**, table: Contoso Madrid only, Sales amount **366,058.87**, Orders **484**. |

Expected values for every lab user (from `src/reference/expected/summary.json`, `rls`):

| User | Stores | Sales amount | Orders |
|---|---|---|---|
| alex.demo | Contoso Lisboa | 389,707.34 | 483 |
| sam.demo | Contoso Madrid | 366,058.87 | 484 |
| riley.demo | Contoso Lisboa, Contoso Online, Contoso Porto | 1,111,159.04 | 1,446 |
| taylor.demo | Contoso Paris | 385,184.07 | 510 |

Optional B-roll (code scenes, no sign-in needed), from the episode folder:

```bash
python3 src/tools/build_dataflow.py --check                  # dataflow item matches the queries
python3 src/tools/check_contract.py --model src/ContosoSales.SemanticModel/definition
dotnet src/TmdlLoad/bin/Debug/net10.0/tmdl-load.dll src/ContosoSales.SemanticModel/definition
```

## Things to record and report (the README and the narration depend on them)

- Does the Git import of the dataflow folder work as is? Which fields did Fabric add or rewrite in `queryMetadata.json`
  after the first commit from the service? (Send the diff.)
- Refresh duration of the dataflow with `SalesExport` not loaded (referenced by five queries). Learn's Gen1 guidance warns
  that referencing queries with load disabled can re-evaluate them; if the duration looks high, set *Enable staging* on
  `SalesExport` and record the difference.
- Does the Dataflows connector in Desktop list only the six entities (staging queries hidden)?
- What *Manage permissions* and the Security page show exactly, and whether `sam.demo` needs Build, or Read, or workspace
  access to open a thin report from another workspace.
- Whether the REST links (`datasets/upstreamDataflows`) list a Gen2 dataflow (SM003).

## Masking
- Workspace, dataflow and model IDs, and the SharePoint site URL: only in variables or parameters set off camera; blur
  browser URLs (`pipeline/mask.js`).
- The tenant domain shows in the permissions pickers, the InPrivate account menu and the `UpnDomain` parameter: blur it.
- The audit output uses names only (no IDs, no e-mail); check it anyway.

## Tear-down
- Unpublish nothing from episode 6 unless the maintainer says so. Delete the thin report and, if no later episode needs it,
  the model, the dataflow and the workspace *Contoso Data (Lab)*; delete the *Store Managers* / *Head Office* members first.
- Disconnect Git (workspace settings) and delete the Azure DevOps project `mglab-pbi-ep07`.
- Delete the SharePoint site *ContosoBikesData* (and empty its recycle bin) if no later episode uses it.
- Don't commit the project with the real `WorkspaceId`, `DataflowId`, `UpnDomain` or site URL. No Azure cost; trials only.
