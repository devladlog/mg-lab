# Demo shot list — SharePoint #6 Search and metadata

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none (no Hyper-V VM, no Azure resource group) |
| Tenant | **SharePoint** in the lab tenant (Microsoft 365 E5 trial, until 20 Dec 2026): term store, site collection search schema, SharePoint search (KQL). No SharePoint Premium / Syntex. Episode 3's communication site `/sites/Purchasing` (*Contoso Purchasing*) with episode 4's **Supplier Documents** library filed **with `-IncludeIncomplete`** (the Adventure Works contract without expiry date) plus `scan_0001.txt` dragged in, and with Fabrikam, Northwind Traders, Tailspin Toys and Adventure Works files present. Episode 5's permission changes and Confidential label don't matter here (its tear-down may or may not have run). Created here: term group *Contoso Purchasing* → term set *Purchasing Categories* (14 terms with fixed IDs), site column `PurchCategory` added to the *Purchasing Document* content type and the library, category values on the files, aliases/mappings on RefinableString00/01 and RefinableDate00/01, a library re-index (all removed in tear-down unless episode 7 keeps them) |
| Lab users | `labadmin` (Lab Admin, the recording account) only: runs the script, the browser steps and the search queries (results are security-trimmed to labadmin, who can read the whole library). No other lab user is needed |
| Roles | `labadmin`: **SharePoint Administrator** (from episode 3), **site collection admin** on the site (search schema, re-index), and **Term Store admin** — add labadmin under SharePoint admin center → *Content services → Term store* → *Admins* in set-up if it isn't listed, and remove it in tear-down |
| Entra | The existing "MG Lab PnP" app registration (delegated) |
| Licences / trials | lab E5 trial licence for labadmin; cost €0 |
| Timing | Two sessions: day 1 provisioning + schema mapping + re-index; day 2 (after the crawl, note how long it took) the search tests. Keep the date episode 4's files were generated for `-Today` |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js`, signed in to the lab tenant as labadmin, for the term store, library and search schema screens |

The code scenes are real output from this folder (plan lint, KQL lint, Pester). The four `screen` scenes need the lab
tenant. **Needs tenant:** `Invoke-MgTaxonomyProvisioning`, `Invoke-MgCategoryColumn`, `Invoke-MgCategoryTagging`,
`Get-MgSiteSearchMapping`, `Invoke-MgSearchTest`, `Request-PnPReindexList` and every `-SiteUrl` path of
`Invoke-SearchMetadata.ps1`. Locally they are covered only by Pester tests that mock the real PnP cmdlets (parameter
names and types are checked).

Plan **two sessions**: provisioning + mapping + re-index on day 1, the search tests after the crawl (day 2, or a few
hours later; note how long it took).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab tenant, Microsoft 365 E5 trial | term store, search schema, KQL: any SharePoint plan. No SharePoint Premium | €0 (trial until 20 Dec 2026) |
| The episode 3 **Contoso Purchasing** site with the episode 4 **Supplier Documents** library filed | run episode 4 with `-IncludeIncomplete` (the Adventure Works contract without expiry date is a test case) and drag in `scan_0001.txt` as in episode 4 | €0 |
| **Term Store admin** (SharePoint admin center → Term store → *Admins*) for `labadmin` | needed to create the term group | €0 |
| **Site collection admin** on the site for `labadmin` | search schema page and re-index | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app | €0 |
| PowerShell 7.4+ with PnP.PowerShell 3.x and Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |

Important: the episode 4 sample files are dated relative to the day they were generated. Pass `-Today` with **that
date** to `-RunTests` if the tests run on another day (e.g. `-Today 2026-12-07`), or the "next 60 days" window shifts.

## Set-up (day 1, before recording)
```powershell
cd series/sharepoint/episodes/06-search-metadata
Invoke-Pester ./tests -Output Detailed                        # expect 31 passed
$p = @{ PlanPath = './src/search/search-plan.json'; TermSetPath = './src/search/purchasing-categories.termset.json'
        TestsPath = './src/search/search-tests.json'; SiteUrl = 'https://<lab-tenant>.sharepoint.com/sites/Purchasing'
        ClientId = '<MG Lab PnP client id>' }                 # never on screen unmasked
./src/Invoke-SearchMetadata.ps1 @p -Provision -WhatIf          # 2 + 14 AddTerm rows, AddColumn, AddFieldLink, Tag rows
./src/Invoke-SearchMetadata.ps1 @p -Provision
```
Check (not verified locally, note in README if different):
- The terms have the JSON IDs (term store → Facilities → *Unique Identifier* ends in `...1e10`).
- The Category column shows on Contract and Invoice in the library (inherited through `-UpdateChildren`).
- `Set-PnPListItem -Values @{ PurchCategory = '<term id>' }` set the category (the library shows *Cleaning* on the
  Fabrikam files). If it didn't, try `'Contoso Purchasing|Purchasing Categories|Facilities|Cleaning'` and fix the module.

### Map the search schema (day 1, in the browser; this is the `schema` screen)
Site → **Settings → Site information → View all site settings → Site Collection Administration → Search Schema**.
On *Crawled Properties*, filter `ExpiryDate`, `InvoiceDate`, `Supplier`, `PurchDepartment` and **note which names
SharePoint lists** (`ows_q_DATE_ExpiryDate` and/or `ows_ExpiryDate`, …). If none is listed yet, the library hasn't been
crawled since episode 4: wait, or request a re-index first. Then, on *Managed Properties*, filter "Refinable" and edit:

| Managed property | Alias | Map to (crawled property) |
|---|---|---|
| RefinableString00 | PurchSupplier | Supplier (`ows_q_TEXT_Supplier` or `ows_Supplier`) |
| RefinableString01 | PurchDept | PurchDepartment (`ows_q_CHCS_PurchDepartment` or `ows_PurchDepartment`) |
| RefinableDate00 | PurchExpiry | ExpiryDate (`ows_q_DATE_ExpiryDate` or `ows_ExpiryDate`) |
| RefinableDate01 | PurchInvoiceDate | InvoiceDate (`ows_q_DATE_InvoiceDate` or `ows_InvoiceDate`) |

Write the crawled property you picked into `search-plan.json` (`"crawledProperty": "..."` on each mapping) so the plan
records what the lab really uses. Then:
```powershell
./src/Invoke-SearchMetadata.ps1 @p -CheckMapping -Reindex      # expect "No findings" for the mappings
```

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/termstore.jpg` — scene `termstore`**
   SharePoint admin center → **Content services → Term store**, *Contoso Purchasing → Purchasing Categories* expanded,
   **Facilities** selected, *General* tab with the Unique Identifier visible (the GUID is fictional, no need to mask).

2. **`screens/library-category.jpg` — scene `library`**
   Supplier Documents, a view with Name, Supplier, Category, Expiry date (inside the document sets or a flat view
   "Show all items without folders"): Fabrikam → Cleaning, Northwind Traders → Paper and Toner, Tailspin Toys →
   Merchandise, Adventure Works → Vehicle Leasing, scan_0001.txt empty.

3. **`screens/schema.jpg` — scene `schema`**
   *Edit Managed Property* page for **RefinableDate00**: Alias *PurchExpiry*, the mapping to the ExpiryDate crawled
   property. Second capture if possible: the managed properties list filtered "Refinable" showing the four aliases.

4. **`screens/search-tests.jpg` — scene `searchrun`** (day 2, after the crawl)
   ```powershell
   ./src/Invoke-SearchMetadata.ps1 @p -CheckMapping -RunTests -Today <date the episode 4 files were generated>
   ```
   Expected: the four mappings read back, "No findings", six PASS lines, "6 passed, 0 failed". **Record what it really
   says.** Check in particular:
   - *Facilities, the whole branch*: `owstaxIdPurchCategory:"GPP|#<id>"` is documented for SharePoint Server; if it
     returns nothing in SharePoint Online, record it, change the test (e.g. map `ows_taxId_PurchCategory` to
     `RefinableString02` and query `GP0|#` on the child term) and add the finding to README.
   - *Refine by supplier*: the refiner rows come back with `RefinerName` / `RefinementName` keys.
   - *Contracts with no expiry date*: `NOT PurchExpiry>=1900-01-01` returns the Adventure Works contract.
   - Optional check for the gotcha scene: `Submit-PnPSearchQuery -Query 'ExpiryDateOWSDATE<2027-01-01' -RelevantResults`
     — note what it returns (the lint says it can't work as a date range). Don't put it on screen unless it confirms.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in the address bar and in `$p.SiteUrl`; PnP client id; device-login code; admin account and avatars.
- Search result paths in the terminal contain the tenant host: the `-RunTests` output prints only names and counts;
  if `-CheckMapping` or an error prints a URL, blur it.
- File and supplier names are fictional.

## Tear-down
```powershell
Connect-PnPOnline -Url $p.SiteUrl -ClientId $p.ClientId -DeviceLogin
Remove-PnPField -List 'Supplier Documents' -Identity PurchCategory -Force
Remove-PnPField -Identity PurchCategory -Force                 # if the content type link blocks it, remove it from 'Purchasing Document' first
Remove-PnPTermGroup -Identity 'Contoso Purchasing' -Force      # if it refuses because the group isn't empty, delete the term set in the term store first
```
Remove labadmin from the term store *Admins* if it was added for this episode. In the search schema, clear the alias and mapping on the four Refinable properties (they're shared by the site
collection). Keep everything if episode 7 builds on it.
