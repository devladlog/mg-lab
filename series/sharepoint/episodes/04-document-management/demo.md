# Demo shot list — SharePoint #4 Document management

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **SharePoint** in the lab tenant: episode 3's communication site `/sites/Purchasing`. Changed here: Document Sets and Document ID Service features (site collection), 8 site columns, 4 content types, library *Supplier Documents* (all removed in tear-down; features may stay) |
| Lab users | `labadmin` (the recording account): site collection admin, runs the script and drags the file in; Modified By shows labadmin (mask) or upload as Alex Demo (`alex.demo`, site member) |
| Entra | The existing "MG Lab PnP" app registration (delegated) |
| Licences / trials | lab E5 licences; cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js` for the SharePoint screens |

The code scenes are real output from this folder (lint, filing plan, Pester). The three `screen` scenes need the lab
tenant. **Needs tenant:** `Invoke-MgDocMgmtProvisioning`, `Invoke-MgFiling`, `Get-MgLibraryAudit` and every
`-SiteUrl` path of `Invoke-DocumentManagement.ps1`. Locally they are covered only by Pester tests that mock the real
PnP cmdlets (parameter names and types are checked), and the entry script by a parse check and its offline modes.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab Microsoft 365 tenant with SharePoint | existing lab tenant | €0 (existing licences) |
| The episode 3 **Contoso Purchasing** communication site | or any test site; it must **not** use content types from the content type hub (DM011) | €0 |
| **Site collection admin** on that site | enabling the Document Sets and Document ID Service features is site-collection scoped | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app | €0 |
| PowerShell 7.4+ with PnP.PowerShell 3.x and Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/04-document-management
Invoke-Pester ./tests -Output Detailed                       # expect 31 passed
./src/New-SampleDocuments.ps1 -Path ./src/sample-files        # on the recording day: expiry dates are relative to today
$site = 'https://<lab-tenant>.sharepoint.com/sites/Purchasing'   # never on screen unmasked
$app  = '<MG Lab PnP client id>'
./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -PlanPath ./src/docmgmt/filing-plan.json `
    -FilesPath ./src/sample-files -SiteUrl $site -ClientId $app -WhatIf
```
The `-WhatIf` plan should list 2 features, 8 columns, 4 content types, 9 field links, the document set settings, the
library, 3 list content types, RemoveListCT Document, 1 default value, then 3 document sets and 5 uploads (4 and 6
with `-IncludeIncomplete`). Dark terminal theme, font 18+, clear the screen before each capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/provision.jpg` — scene `provision`**
   ```powershell
   ./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -PlanPath ./src/docmgmt/filing-plan.json `
       -FilesPath ./src/sample-files -SiteUrl $site -ClientId $app -IncludeIncomplete
   ```
   Capture the lint ("No findings"), the filing plan table, the provisioning rows and the AddDocumentSet / Upload
   rows. The run ends with a first audit; that's fine, scene `audit` uses a second run. **If any cmdlet fails,
   record the error** and fix the module/README before re-recording — don't stage it.
   Check on this run (not verified locally):
   - Contract and Invoice show **Supplier** and **Department** (inherited from Purchasing Document): Site settings →
     Site content types → Contract. If they don't, `Add-PnPContentType -ContentTypeId` didn't inherit field links;
     note it as a gotcha and add the parent's fields explicitly.
   - The Document ID column gets values (Library settings → the column **Document ID**). Note how long it takes.

2. **`screens/library.jpg` — scene `library`**
   Browser: **Supplier Documents** with the four **Supplier File** document sets (Adventure Works, Fabrikam,
   Northwind Traders, Tailspin Toys). Second capture for the same scene if possible: inside **Fabrikam**, a view
   with Name, Content type, Contract number, Expiry date, Department, Document ID; and the **New** menu showing
   Contract and Invoice only (no generic Document). Check that **Expiry date** shows the same day as in the file name
   (date-only values; if it's one day off, record it and add it to the gotchas).

3. **`screens/audit.jpg` — scene `audit`**
   In the browser, drag `src/sample-files/scan_0001.txt` into the library root (it becomes a Contract, the default
   content type). Then:
   ```powershell
   ./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -Audit -SiteUrl $site -ClientId $app
   ```
   Expected: DA001 on the Adventure Works contract (ExpiryDate) and on scan_0001.txt (Supplier, ContractNumber,
   ExpiryDate), DA005 on Tailspin Toys (expired), DA004 on Fabrikam (expires in 30 days), possibly DA006 if document
   IDs aren't assigned yet. **Record what it really says** and adjust the narration of scene `audit` if needed.
   Note: the browser upload of scan_0001.txt is itself a check of the Learn article — see whether it prompted for
   the required columns.

Optional insert for scene `gotcha`: the upload of scan_0001.txt in the browser, showing no prompt for required
fields (only if that's what happens).

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in the address bar and in the `$site` terminal line; PnP client id; device-login code.
- Account avatars and names (Modified By, Checked out to): use the demo account shown as "Alex Demo".
- The document IDs contain a tenant-generated prefix: blur the Document ID column if the prefix reveals the tenant.
- File names and supplier names are fictional (Fabrikam, Northwind Traders, Tailspin Toys, Adventure Works).

## Tear-down
```powershell
Connect-PnPOnline -Url $site -ClientId $app -DeviceLogin
Remove-PnPList -Identity 'Supplier Documents' -Recycle -Force
'Supplier File', 'Contract', 'Invoice', 'Purchasing Document' | ForEach-Object { Remove-PnPContentType -Identity $_ -Force }
'Supplier', 'PurchDepartment', 'ContractNumber', 'ContractValue', 'ExpiryDate', 'InvoiceNumber', 'InvoiceDate', 'InvoiceAmount' |
    ForEach-Object { Remove-PnPField -Identity $_ -Force }
```
If deleting a content type fails because it's still in use, empty the site recycle bins
(`Clear-PnPRecycleBinItem -All -Force`) and retry. The two features can stay on; disable them with `Disable-PnPFeature -Scope
Site` if the site is reused. Delete `src/sample-files/` locally (git-ignored).
