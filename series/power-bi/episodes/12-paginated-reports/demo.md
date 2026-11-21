# Demo shot list — Power BI #12 Paginated Reports

## Lab environment

Tenant work is real: the Power BI service on the lab tenant (workspace `Contoso Sales (Lab)` on the Fabric trial capacity), with the
semantic model `ContosoSales` of episode 1 published there, and Power BI Report Builder plus PowerShell 7.2+ and Python 3.10+ on the
Windows laptop (`series/LAB.md`). CON-SQL01 (10.50.0.30) and the Hyper-V network are **not used** in this episode: the report reads the
semantic model, not SQL Server. No Azure resource is created, so there is no resource group to tear down.

| What | Details | Cost |
|---|---|---|
| Fabric trial capacity | the workspace must be on a Fabric (or Premium) capacity to host paginated reports | free (trial) |
| Workspace | `Contoso Sales (Lab)`, with the semantic model `ContosoSales` published from episode 1 (Import mode; refreshed at least once) | free |
| Users | `alex.demo` (admin of the workspace, Build permission on the model). The export is run as this user | — |
| Tools | Power BI Report Builder (current release), `pwsh` 7.2+ with the MicrosoftPowerBIMgmt module, Python 3.10+ with `pdfplumber` | free |

## What was verified where

| Step | Verified in the container | Needs tenant / Report Builder (recording day) |
|---|---|---|
| RDL structure | valid against Microsoft's RDL 2016/01 XSD; lint rules RL000-RL008 and mutated copies | **whether Report Builder opens the file as it is**, and the service accepts it (needs tenant) |
| DAX, `@Year` binding, field names | the DAX file equals the dataset text; every `Fields!` is declared | **the DAX run against the model**: the DataField names (`Store[Store]`, `[Sales Amount]`) and the `@Year` query parameter name are written from knowledge of the designer output, not tested (needs tenant) |
| Expected numbers | `expected.py` and the contract from the CSV files (5 stores x 12 months for 2025) | that the report's numbers equal them (needs tenant) |
| PDF check | `verify_pdf.py` against a **simulated** PDF drawn with reportlab from the contract (a pass, a changed figure, blank pages) | against the real export (needs tenant) |
| REST calls (Imports, ExportTo, status, file) | Pester tests, requests asserted, mocks shaped like the Learn samples | **the real calls**, the multipart upload of a raw .rdl, the identity needed for a report on a semantic model (needs tenant) |

## Setup (off camera, once)

1. Tenant (needs tenant): the workspace on the trial capacity, the model `ContosoSales` published and refreshed.
2. Rebuild and check the files: `python3 src/tools/build_rdl.py --check`, `python3 src/tools/rdl_lint.py src/report/ContosoStoreStatement.rdl`.
3. Expected numbers: `python3 src/tools/expected.py 2025` (60 store-month rows, 5 stores). The contract is `src/contract/store-statement-2025.json`.
4. Report Builder (needs tenant): open the .rdl, sign in when it asks for the data source, **Run** with Year 2025. Write down every message and every change Report Builder makes when it saves the file.
5. PowerShell 7 terminal: `Connect-PowerBIServiceAccount` as `alex.demo` (a sign-in done by the person recording, never by the build). Rehearse with `-WhatIf`:
   `./src/ps/Invoke-StatementRun.ps1 -WorkspaceId <id> -ReportId <id> -Year 2024,2025 -Username <alex.demo upn> -WhatIf`.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen (needs tenant unless stated) |
|---|---|---|
| `builder` | `screens/report-builder.jpg` | Report Builder with `src/report/ContosoStoreStatement.rdl`: the Report Data pane (data source `ContosoSales`, dataset `StoreSales`, parameter `Year`), **Run**: store page 1 (Contoso Lisboa, 2025) with repeated headers and `Page 1 of 5` |
| `preview` | `screens/service-preview.jpg` | After `Import-PbiRdl` (or **Publish** from Report Builder): the paginated report in `Contoso Sales (Lab)`, Year 2025, **View report**, then 2024. Show the footer and the page count |
| `pdf` | `screens/pdf-verify.jpg` | `Invoke-StatementRun.ps1 -Year 2025 ...` then `out/statement-2025.pdf` beside the terminal: five pages, one store each, and the `verify_pdf.py` verdict. If it reports mismatches, keep them in the video and explain them (rounding of `Margin %` is the first suspect) |

## Not a screen scene, but record it

- The blank-page gotcha: in Report Builder set the body width to 7.2in, export the PDF, show the doubled page count, set it back to 6.5in. Run `rdl_lint.py` on the bad file to show RL001.
- If the export returns an error about the identity or the data source, show the message: Learn lists the cases (a report on a semantic model needs an effective identity; XMLA endpoint settings; no export with an identity when the model uses single sign-on).
- With a Premium Per User license the export API allows one request in five minutes (Learn): export 2024 and 2025 with a pause, or use the trial capacity.

## Masking

- Mask the tenant name, the capacity name and any e-mail address except `alex.demo`.
- Workspace, report and export ids in the address bar and in the terminal: crop or blur them.
- Do not show the token of `Connect-PowerBIServiceAccount`; clear the terminal history afterwards.

## Tear-down

1. Delete the paginated report `ContosoStoreStatement` from `Contoso Sales (Lab)` (the semantic model stays: it belongs to episode 1).
2. Delete `out/` (the exported PDFs). `Disconnect-PowerBIServiceAccount`.
3. Nothing to delete in Azure for this episode.
