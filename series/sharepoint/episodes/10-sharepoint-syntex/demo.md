# Demo shot list — SharePoint #10 SharePoint Syntex (document processing)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Hyper-V | none (the shared lab network 10.50.0.0/24 is not used) |
| Azure | **A resource group `rg-mglab-sharepoint-10` in West Europe**, in the lab subscription, only to link pay-as-you-go billing (Microsoft 365 admin center → Settings → Org settings → Pay-as-you-go services). The group holds no resources; the usage shows under it in Cost Management. Expected cost: about 0.10 USD for the recording (19 pages at 0.005 USD, once per model), a few cents more for re-runs, against the lab's 30 EUR budget |
| Tenant | SharePoint Online in the lab tenant (Microsoft 365 E5 trial, until 20 Dec 2026). From earlier episodes: `/sites/Purchasing` with the library `SupplierDocuments` (episode 4). Created here: a content center `/sites/ContentCenter`, the model *Supplier Contract* with its content type, the two extractor columns and the *Classification Date* column on `SupplierDocuments` |
| Lab users | `labadmin` (SharePoint Administrator, **and Owner or Contributor on the Azure subscription**: Learn requires both for the billing setup); `alex.demo` (Alex Demo, owner of the Purchasing site, uploads the files and teaches the model) |
| Entra app | The existing "MG Lab PnP" app (delegated), consented for SharePoint on `/sites/Purchasing`. Nothing new |
| Licences | lab E5 for people; **no SharePoint Advanced Management, no AI Builder credits needed** (unstructured model). The free pay-as-you-go capacity ended in June 2026, so expect to be billed |
| Recording machine | The Windows lab laptop: PowerShell 7.4+, PnP.PowerShell 3.x, Pester; browser with `pipeline/mask.js` |

The code scenes are real output from this folder (lint, cost, Pester). **Needs tenant:** the whole browser part (billing,
content center, teaching the model, applying it), `Send-MgSampleFiles`, `Get-MgLibraryState` and the `-Upload` /
`-Report` paths of `Invoke-DocProcessing.ps1`. Locally those two functions are covered only by Pester tests that mock
the real PnP cmdlets (parameter names are checked; the shapes of the objects are what the docs say).
**The model cannot be created by script**: PnP's Syntex cmdlets are obsolete, so the teaching is a browser step.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Episode 4's `SupplierDocuments` library on `/sites/Purchasing` | The plan applies the model to it. If it is called something else, change `appliesTo` in `contoso-docproc.json` | €0 |
| `labadmin` is SharePoint Administrator and Owner/Contributor on the Azure subscription | Needed to link billing | €0 |
| Azure subscription in the same tenant, resource group `rg-mglab-sharepoint-10` | `az group create` is **not** run by this episode's scripts; create it in the portal, West Europe | ≈ €0 (empty group) |
| PowerShell 7.4+, PnP.PowerShell 3.x, Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |
| The sample PDFs | `./src/New-SampleDocuments.ps1 -Path ./src/sample-files` (12 files, generated fresh, not committed) | €0 |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/10-sharepoint-syntex
Invoke-Pester ./tests -Output Detailed                                      # expect 66 passed
./src/New-SampleDocuments.ps1 -Path ./src/sample-files
./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json -SamplesPath ./src/sample-files   # No findings, 19 pages
$t = @{ TenantUrl = 'https://<lab-tenant>.sharepoint.com'; ClientId = '<MG Lab PnP client id>' }   # never on screen unmasked
```

Browser steps, **do these the day before** (billing and sync can take time) and write down what you see:

1. **Billing.** Microsoft 365 admin center as `labadmin` → Settings → Org settings → *Pay-as-you-go services* → link the
   subscription, resource group `rg-mglab-sharepoint-10`, region West Europe. Note the page that confirms it.
2. **Content center.** SharePoint admin center → Sites → Active sites → Create → Browse more sites → *Content center*.
   Name *Contoso Content Center*, address `/sites/ContentCenter`, owner `alex.demo`.
3. **Teach the model.** In the content center: Models → New → *Teach the system to read your documents* (unstructured) →
   name **Supplier Contract**. Add the six `training/contract-*.pdf` as positive examples and the three
   `training/invoice-*.pdf` as negatives. Create an explanation (for example a phrase list: "Supply Agreement",
   "Contract number", "Expiry date"). Add two extractors, **Contract number** and **Expiry date**, and label the value in
   **at least five** of the contracts each (the plan says 5; the lint DP003 would complain about 4). Test, then *Apply* to
   `Purchasing` → `SupplierDocuments`.
4. Check in the library: the content type *Supplier Contract*, the two columns and *Classification Date* exist
   (library settings → content types, columns). Write down their **internal names**: they are the "Not verified yet" list in README.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/billing.jpg` — scene `billing`** (browser)
   Microsoft 365 admin center → Org settings → Pay-as-you-go services, the linked subscription and resource group
   `rg-mglab-sharepoint-10`; beside it the content center home with the model *Supplier Contract* open (the extractors
   *Contract number* and *Expiry date* and the example counts). Mask the subscription id and the tenant name.

2. **`screens/upload.jpg` — scene `upload`** (terminal)
   ```powershell
   ./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Upload ./src/sample-files/inbox -WhatIf
   ./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Upload ./src/sample-files/inbox
   ```
   Capture the `-WhatIf` run (three `Upload` lines, nothing written) and the real run (the same three lines, after
   the device-code sign-in done off camera). Run the real one a second time: no `Upload` lines (the files are there already).

3. **`screens/library.jpg` — scene `library`** (browser, the next day if classification is slow)
   `SupplierDocuments` as Alex Demo, with the columns *Content type*, *Contract number*, *Expiry date*, *Classification Date*
   shown: `scan_0001.pdf` classified as *Supplier Contract* with both values; `scan_0002.pdf` (an invoice) and
   `meeting-notes.pdf` not classified (Learn: classification can take up to 24 hours). **Record what really happens**,
   including empty columns, and say so in README.

4. **`screens/report.jpg` — scene `report`** (terminal)
   ```powershell
   ./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Report
   ```
   Capture the counts line, the filled and empty counts per column and the findings (for example `DL006` if an extractor
   missed a value, `DL005` for a file that is still unclassified after 24 hours). If the report says something wrong
   about what the library shows, fix `Get-MgLibraryState` and README, do not edit the screenshot.

5. (Optional, not a `screen` scene) **Cost.** Azure portal → Cost Management → the resource group `rg-mglab-sharepoint-10`:
   usage can take up to 24 hours to show. Compare it with the 0.10 USD of the estimate and note the difference in README.

## Masking
- Tenant host, the client id, device-login codes, the Azure subscription id and the billing account.
- Account pictures and the admin account name. Site, library and people names are fictional.
- The sample PDFs are fictional (Contoso, Fabrikam, Litware and similar): no mask needed.

## Tear-down
1. SharePoint: delete the content type *Supplier Contract* and the extractor columns from `SupplierDocuments` (or remove
   the model from the library first in the content center: Models → Supplier Contract → Applied libraries), delete the uploaded
   files, then delete the model in the content center.
2. SharePoint admin center → delete the site `/sites/ContentCenter` (and empty it from *Deleted sites* if you want it gone now).
3. **Stop billing:** Microsoft 365 admin center → Org settings → Pay-as-you-go services → disconnect the subscription, then
   delete the resource group `rg-mglab-sharepoint-10` in the Azure portal. Check Cost Management one day later: no new usage.
4. Delete `./src/sample-files` (generated, untracked).
