# DEVLADLOG SharePoint #10 — SharePoint Syntex (document processing), plan, pre-flight and cost as code

Contoso Purchasing keeps its supplier files in the `SupplierDocuments` library ([episode 4](../04-document-management/)).
Contracts arrive as `scan_0001.pdf`, nobody fills in the expiry date, and renewals are found too late. Syntex is the
answer on paper: a model that recognises a *Supplier Contract* and pulls out the **contract number** and the **expiry
date**. Microsoft now calls it **document processing** (the features are the same), and it is a pay-as-you-go service.

**The honest part first.** The model itself cannot be scripted. It is taught in a *content center* in the browser
(classifier, extractors, example files), and PnP.PowerShell's Syntex cmdlets (`Get-PnPSyntexModel`,
`Publish-PnPSyntexModel`, `Request-PnPSyntexClassifyAndExtract` and the rest) are marked obsolete in PnP's development
documentation: *"obsolete and no longer does anything, as SharePoint Syntex is no longer supported. It only writes a
warning and will be removed in a future version"*. Version 3.1.0 still lists them; this episode does not call them.
What can be code, and is tested, is everything around the model:

- **lint the plan** (`DP001`–`DP009`): billing set up, model types, training minimums, languages, library paths,
  expected file types, several models on one library, the budget, and the AI Builder warning
- **pre-flight the files** (`FP001`–`FP008`) before they reach a library: file types, page counts, sizes, image and
  page dimensions, and **count the billable pages** the way Learn's meters count them
- **estimate the monthly cost** from the plan or from real files, with the meters from Learn
- **read the library back** (`DL001`–`DL007`): is the model's content type there, is the *Classification Date* column
  there, which files were classified, which extracted columns are empty

| Path | What it is |
|---|---|
| [`src/MgDocProc.psm1`](src/MgDocProc.psm1) | The module: `Test-MgDocProcPlan`, `Test-MgFile`, `Test-MgTrainingSet`, `Get-MgBillablePages`, `Get-MgCostEstimate`, `Get-MgMeter`, `New-MgPdf`, `Get-MgPdfInfo`, `Get-MgImageSize`, `Get-MgExtractionReport`, `Test-MgLibraryLive`, `Send-MgSampleFiles`, `Get-MgLibraryState` |
| [`src/docproc/contoso-docproc.json`](src/docproc/contoso-docproc.json) | The plan: billing, content center, one unstructured model *Supplier Contract* (6 positive, 3 negative examples, extractors *Contract number* and *Expiry date*, 5 labelled files each) applied to `SupplierDocuments`, expected volume, budget |
| [`src/docproc/meters.json`](src/docproc/meters.json) | The pay-as-you-go meters from Learn, with source URL and the date they were read (2026-11-21) |
| [`src/bad/bad-docproc.json`](src/bad/bad-docproc.json) | A plan with the usual mistakes: the lint demo (8 errors, 8 warnings) |
| [`src/New-SampleDocuments.ps1`](src/New-SampleDocuments.ps1) | Writes 12 fictional PDFs: `training/` (6 contracts, 3 invoices as negative examples) and `inbox/` (an unnamed contract, an invoice, meeting notes) |
| [`src/Invoke-DocProcessing.ps1`](src/Invoke-DocProcessing.ps1) | Lint + cost → pre-flight of files → `-Upload` → `-Report` |
| [`tests/MgDocProc.Tests.ps1`](tests/MgDocProc.Tests.ps1) | 66 Pester tests; the tenant tests mock the **real** PnP cmdlets |

The sample PDFs are real, valid, text PDFs (the writer is in the module; the files were checked with `qpdf --check`
and `pdftotext`). They are not scans, so OCR is not what is being exercised. Dates in them are relative to the day you
generate them.

## Run it

```powershell
cd src
./Invoke-DocProcessing.ps1 -PlanPath ./bad/bad-docproc.json                    # 8 error(s), 8 warning(s), 2,400 USD a month
./New-SampleDocuments.ps1 -Path ./sample-files
./Invoke-DocProcessing.ps1 -PlanPath ./docproc/contoso-docproc.json -SamplesPath ./sample-files   # No findings; 19 pages, 0.10 USD
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it the tenant tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 66, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.1.0, qpdf for the PDF cross-check):
**66 passed, 0 failed, 0 skipped**; the commands above print the counts shown. PSScriptAnalyzer reports no errors
(warnings: `Write-Host` in the entry script, plural nouns, `ShouldProcess` on helper functions).

In the lab (needs tenant; see demo.md for the browser steps that must come first):

```powershell
$t = @{ TenantUrl = 'https://contoso.sharepoint.com'; ClientId = '00000000-0000-0000-0000-000000000000' }
./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Upload ./src/sample-files/inbox -WhatIf
./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Upload ./src/sample-files/inbox
./src/Invoke-DocProcessing.ps1 -PlanPath ./src/docproc/contoso-docproc.json @t -Report
```

## Licensing and cost (what each part needs)

| Feature | Needs | Notes |
|---|---|---|
| Teach a model in the content center | A content center (a SharePoint admin creates it), pay-as-you-go billing for applying it | Learn: an unlicensed user can create models but can't apply them |
| Apply a model to a library, classify, extract | **Pay-as-you-go billing**: an Azure subscription in the same tenant and a resource group, linked in the Microsoft 365 admin center by a SharePoint or Global Administrator who has rights on the subscription | Billed per transaction; Cost Management can lag up to 24 hours |
| The script (`-Upload`, `-Report`) | Delegated SharePoint access to the site through your own Entra app (`-ClientId`) | `Connect-PnPOnline -DeviceLogin`, no Graph permissions needed |
| Not needed | SharePoint Advanced Management, AI Builder credits (for unstructured) | Structured and freeform models rest on AI Builder |

Meters (USD, from [`meters.json`](src/docproc/meters.json)): unstructured **0.005** per page, sheet, slide or file;
prebuilt **0.01** per page; structured and freeform **0.05** per page; OCR 0.001 per page; image tagging 0.001;
taxonomy tagging 0.05 per document; autofill columns 0.005. Training is free. Learn: processing is counted **per model
applied to the library, on upload and on every update**, whether or not anything was classified.

The plan's volume is **per library**: 40 documents a month × 3 pages × (1 + 0.5 updates) = 180 transactions = **0.90 USD**
a month for one model on one library. Two models on that library would cost twice that, five libraries five times.
The one-off upload of the 12 sample files is 19 pages = about 0.10 USD (the 6 training files are only used in the
browser and cost nothing; the entry script counts every file in the folder you give it).

The free monthly capacity (100 unstructured pages and others) ran **through June 2026**; it has ended.

## The rules

| Rule | Checks | Source |
|---|---|---|
| DP001 | Billing without Azure subscription, resource group or region | Pay-as-you-go prerequisites |
| DP002 | Unknown model type; an *enterprise* model with no content center | Enterprise models are created in a content center, local ones in a library |
| DP003 | Unstructured model with fewer than 5 positive or 1 negative example file; an extractor labelled in fewer than 5 files | Train an unstructured model |
| DP004 | Prebuilt model language not supported (contract: English only; invoice: en, es, de, fr, it, pt, nl; receipt: 17 languages) | Prebuilt requirements |
| DP005 | Library path isn't `/sites/<site>/<library>` (warning: subsites are not supported) | Requirements and limitations |
| DP006 | Two models on one library (warning: each one processes and bills every file; the highest average confidence wins) | Multi-model libraries |
| DP007 | An expected file type the model type doesn't process (warning) | Requirements and limitations |
| DP008 | Estimated monthly cost above the plan's budget (warning) | Pay-as-you-go pricing |
| DP009 | Structured or freeform model (warning: the dearest meter; AI Builder credits end of life 1 Nov 2026, some capabilities moving to Copilot in SharePoint) | Pay-as-you-go pricing, AI Builder announcement on Learn |
| FP001 | File type not supported by the model type (`.jpg` for a prebuilt model is a warning: Learn lists `.jpeg`) | Requirements and limitations |
| FP002 | PDF over 500 pages (unstructured) or 2,000 pages (prebuilt) | idem |
| FP003 | Prebuilt file of 50 MB or more | idem |
| FP004 | Image outside 50 × 50 to 10,000 × 10,000 pixels (read from the file header) | idem |
| FP005 | PDF page larger than 11 × 17 inches (A3 passes: Learn names it) | idem |
| FP006 | Encrypted PDF (warning: remove a password lock first) | idem |
| FP007 | Training files over 50 MB together (unstructured), over 500 pages together (prebuilt) | idem |
| FP008 | Text file over 64,000 characters (warning: truncated) | idem |
| DL001 | The library doesn't exist | — |
| DL002 / DL003 | The model's content type isn't on the library / is read-only or sealed | Apply a model; content types that can't be updated can't be used in a model |
| DL004 | No *Classification Date* column | Applying a model adds the content type and the column |
| DL005 | A file not classified 24 hours after it was added (warning) | Learn: classifying can take up to 24 hours |
| DL006 | A classified file with an empty extracted column (warning) | — |
| DL007 | An extractor's column isn't on the library | — |

## Design choices
- **Plan the model, don't script it.** Because the public cmdlets are obsolete, the model's teaching steps live in
  demo.md as browser steps, and the plan only records what they must produce (counts of examples and labels), so the
  lint can say "5 positive and 1 negative, 5 labelled files per extractor" before anyone starts teaching.
- **Count pages the way the meter does.** `Get-MgBillablePages` reads PDF page objects, the Word page count Word stores
  in `docProps/app.xml`, sheets in an Excel workbook, slides in a PowerPoint file, and one per file for text. When a
  file doesn't say (compressed PDF structures, `.doc`, `.xls`, `.ppt`, TIFF) the count is *unknown* and says so instead
  of guessing; the cost estimate leaves those files out.
- **Read the library by column title.** Extractor columns get an internal name when a model is applied; the read-back
  looks the field up by its display title (the extractor's name) and reads the item values by the internal name it found.
- **No domain, no tenant in the plan.** The tenant URL and the client id come in as parameters.

## What we learned / gotchas
- **Syntex is "document processing" now.** Learn's URLs live under `documentprocessing/`; the blog guide's
  "Syntex" is the old name. The features are unchanged.
- **Unlicensed ≠ unable to create.** A user can create a model, but without pay-as-you-go billing it can't be applied.
- **Each model on a library multiplies the bill.** Two models on one library: every file is processed (and billed) by
  both; the file is classified by the one with the highest average confidence, and extraction comes from that one only.
- **A Portuguese contract can't use the prebuilt contract model.** It is English only (DP004). The invoice model takes
  Portuguese; the unstructured model takes Latin-alphabet languages, which is why the plan teaches its own model.
- **Subsites are not supported.** Models run on sites, hub sites, sites associated with a hub, and the primary site of a
  site collection (DP005).
- **Training limits.** At least 5 positive and 1 negative example, a value labelled in at least 5 files per extractor,
  at most 50 MB of training files in a collection. Text is truncated at 64,000 characters, OCR stops at 500 pages.
- **It isn't instant.** Classifying a folder or a large set can take up to 24 hours; usage can take up to 24 hours to
  appear in Cost Management. DL005 waits 24 hours before it complains.
- **The free promo is over, and AI Builder credits end.** The included monthly capacity ran through June 2026. Learn
  announces the end of AI Builder credits (end of life 1 Nov 2026) and says some capabilities are moving to Copilot in
  SharePoint; plan structured and freeform models with that in mind (DP009).
- **Learn disagrees with itself in two places.** The model comparison says OCR-scanned files are limited to 20 pages
  and the requirements page says 500; this episode uses 500 (the requirements page) and FP002 is only as good as that
  page. And "at most 11 × 17 inches, corresponding to Legal or A3" isn't exact (A3 is 11.7 × 16.5 in): FP005 lets A3 through.
- **PowerShell trap found by the tests:** `$byte -shl 8` on a `[byte]` stays a byte and loses the high bits. The image
  header reader multiplies on `[int]` instead (a 640 pixel wide PNG read as 128).
- **Pester trap:** PnP's `-List` and `-Folder` arrive as `PipeBind` objects; compare `$Folder.ServerRelativeUrl`, not the object.

### Not verified yet (lab recording)
- The **internal names** of the extractor columns and of *Classification Date* after a model is applied (the code
  finds them by title; the read-back needs the titles to be what the plan says).
- That the **content type name** equals the classifier's name (`contentType` in the plan), and whether
  `ContentType` comes back by name from `Get-PnPListItem -Fields ContentType` or only the id (the code handles both).
- How long classification takes for three small files, and whether the *Classification Date* column is filled for files
  that were uploaded before the model was applied.
- That pay-as-you-go billing can be linked to the lab's Azure subscription and what the lab's three files cost in
  Cost Management (the estimate says about 0.10 USD).
- Whether the extractors fill the two values on `scan_0001.pdf` (a model trained on 6 small files may miss; the report
  shows that, which is the point).
- Prebuilt field mapping is not exercised at all: only the contract and invoice models' limits are checked, not what
  they extract.

## References
- [Overview of unstructured document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/document-understanding-overview) — what the unstructured model does
- [Set up and manage unstructured document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/unstructured-setup) — pay-as-you-go prerequisite, admin roles
- [Requirements and limitations for unstructured document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/requirements-and-limitations) — file types, OCR limits, 64,000 characters, 50 MB, image and page sizes, sites supported, multi-model libraries
- [Requirements and limitations for prebuilt document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/prebuilt-requirements) — types, 2,000 pages, 50 MB, languages per model
- [Overview of prebuilt document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/prebuilt-overview) — the five prebuilt models
- [Compare custom models for document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/difference-between-document-understanding-and-form-processing-model) — unstructured, freeform, structured; AI Builder credits
- [Create an enterprise model for document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/create-syntex-model) and [Create a model on a local SharePoint site](https://learn.microsoft.com/microsoft-365/documentprocessing/create-local-model)
- [Train an unstructured document processing model](https://learn.microsoft.com/microsoft-365/documentprocessing/create-a-classifier) and [Create an extractor](https://learn.microsoft.com/microsoft-365/documentprocessing/create-an-extractor) — examples, labels, explanations
- [Create a content center](https://learn.microsoft.com/microsoft-365/documentprocessing/create-a-content-center) and [Apply a model](https://learn.microsoft.com/microsoft-365/syntex/apply-a-model) — content type and Classification Date column
- [Set up pay-as-you-go billing for document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/syntex-azure-billing) — Azure subscription and resource group
- [Pay-as-you-go services and pricing](https://learn.microsoft.com/microsoft-365/documentprocessing/syntex-pay-as-you-go-services) — the meters in `meters.json`
- [Try out pay-as-you-go services](https://learn.microsoft.com/microsoft-365/documentprocessing/promo-syntex) — the free capacity, through June 2026
- [Licensing for document processing](https://learn.microsoft.com/microsoft-365/documentprocessing/syntex-licensing) — per-user licences no longer sold
- [Get-PnPSyntexModel (PnP PowerShell)](https://pnp.github.io/powershell/cmdlets/Get-PnPSyntexModel.html) — marked obsolete; the same note is on the other Syntex cmdlets
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Connect-PnPOnline`, `Get-PnPList`, `Get-PnPContentType`, `Get-PnPField`, `Get-PnPListItem`, `Get-PnPFolderItem`, `Add-PnPFile`
- Blog: [SharePoint Syntex — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-06-sharepoint-syntex-complete-guide-2026/) — the current article has no Syntex-specific code (its steps only print messages); this folder is what to put in it
