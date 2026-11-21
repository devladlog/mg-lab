# Demo shot list: DEVLADLOG Power Automate #7, 400 prices in, 256 imported

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant** (DEV environment, SharePoint Online, Excel on the web). Everything below is **needs tenant** and
has not been run there yet.

## Lab environment

No VMs, no Azure resources. Recorded on the recording laptop (lab Windows host): the Power Automate portal and
SharePoint / Excel on the web in a browser signed in as `labadmin`, plus a second browser profile signed in as
`jordan.demo` to upload the file.

| What | Detail | Cost |
|---|---|---|
| Power Platform environment `DEV` (exists) | Solution, connection references, environment variables | none |
| Licences | Lab users have Microsoft 365 E5 (SharePoint, Excel, Outlook, **Office Scripts**: E5 is on Learn's list of licences for Office Scripts in Power Automate). Excel Online (Business), SharePoint and Office 365 Outlook are **standard** connectors: no premium licence or trial needed | none (trials in place) |
| SharePoint site **Purchasing** (from episodes 2, 3, 5; create it if missing) | Libraries: **Price lists** (new) with a folder **Rejected**; **Documents** with *Purchasing catalogue.xlsx* and a folder **Scripts** | none |
| Users | `labadmin` owns the flow and the three connections, and the script; **Jordan Demo** (purchasing) uploads the price list; Lab Admin's mailbox stands in for `purchasing@contoso.com` (set the environment variable to Lab Admin's address in the lab) | none |
| Admin settings | Office Scripts allowed for the lab users (Microsoft 365 admin center → Settings → Org settings → Office Scripts); *People in your organization* sharing links enabled (Learn platform requirement) | none |
| Recording machine | Python 3 + openpyxl to generate the two workbooks, Node 22.13+, `pac` (sign-in off camera) | none |

## Setup (≈ 40 min)

1. **Workbooks.** On the recording machine, from `src/`: `python -m excelfake make-workbooks ../out`. This writes
   `Fabrikam price list 2026-12.xlsx` (table **Prices**, 400 rows, the four bad rows at the end) and
   `Purchasing catalogue.xlsx` (table **Catalogue**, 381 rows, FAB-0007 twice). Upload the catalogue to
   **Purchasing → Documents**. Keep the price list for step 8.
2. **Office Script.** Open *Purchasing catalogue.xlsx* in Excel on the web → **Automate → New script**, paste
   `src/officescript/UpsertPrices.ts` (not the `.d.ts`), save as **Upsert prices**, then **move the `.osts` file to
   Documents/Scripts** (script storage in SharePoint, so *Run script from SharePoint library* can use it and it isn't
   tied to one person's OneDrive). If the Code Editor reports any error, note it in the README and fix the script.
3. **Solution** `Price lists` (unique name `PriceLists`, publisher prefix `cts`). Environment variables (Text):
   `cts_PurchasingSiteUrl` (Purchasing site URL), `cts_PriceListsLibrary` (Price lists), `cts_PriceListsDriveId`
   and `cts_DocumentsDriveId` (leave the defaults for now: the designer picks the drives in step 4 and the export
   in step 6 shows the real values), `cts_UpsertScriptId` (Upsert prices.osts), `cts_PurchasingMailbox`.
4. **Flow** *New → Automation → Cloud flow → Automated* `Supplier price list import`, trigger SharePoint *When a
   file is created (properties only)* on Price lists. Build it from
   `src/solution/Workflows/Supplierpricelistimport-…701.json`, renaming every action to the JSON names:
   - Trigger condition: `@and(endsWith(toLower(triggerBody()?['{FilenameWithExtension}']), '.xlsx'), not(equals(triggerBody()?['{IsFolder}'], true)))`.
   - Excel *List rows present in a table* `List price rows`: Location = Purchasing site, Document Library = Price
     lists, File = `Identifier` from the trigger, Table = `Prices` (custom value), **DateTime Format = ISO 8601**.
     **Settings → Pagination: On, Threshold 5000.**
   - *Condition* `Too many rows` and *Terminate* `Stop not all rows read` (Failed, `TooManyRows`).
   - *Select* `Shape rows`, *Filter array* `Valid rows` and `Rejected rows`, *Select* `Prices for script`: paste
     the expressions from the JSON (switch the Select map to text mode).
   - Excel *Run script from SharePoint library* `Upsert catalogue`: workbook = Documents / *Purchasing
     catalogue.xlsx*, script = Documents / Scripts / *Upsert prices*; parameters prices = output of `Prices for
     script`, supplier = `Fabrikam`, sourceFile = `File name with extension`.
   - *Condition* `Any rejected` → *Create CSV table* `Rejected csv` (custom columns) → SharePoint *Create file*
     `Save rejected rows` in `/Price lists/Rejected`.
   - *Create HTML table* `Big changes table` from `result.bigChanges`; Outlook *Send an email (V2)* `Send summary`.
5. **Lint before saving.** Copy the designer's code view of the Select into a scratch file and run
   `python -m flowkit lint` on the export after step 6 (expects `OK`).
6. **Export and test.**
   ```bash
   pac solution export --name PriceLists --path PriceLists.zip
   pac solution unpack --zipfile PriceLists.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   Compare with the README's "What was not verified here": the Excel parameter keys (`source`, `drive`, `file`,
   `table`, `dateTimeFormat`, `scriptSource`, `scriptDrive`, `scriptId`, `ScriptParameters/...`), the pagination
   setting, the Run script output shape (`body/result`), the trigger's `{Identifier}`/`{IsFolder}`. If they differ,
   keep the export, update `excelfake`, the tests and `tools/build_solution.py`, and note it in the README. Replace
   drive IDs, the script ID and site URLs with the placeholders (`b!000…701`, `https://contoso.sharepoint.com/sites/Purchasing`)
   before committing.
7. **Check the assumed formats in the first real run** (List price rows → Show raw outputs): how a number cell
   arrives (`12.5`?), how `Valid from` arrives with ISO 8601 (`2026-12-01T00:00:00.000Z`?), and without it (copy of the
   flow, DateTime Format empty: serial `46357`?); whether the rejected CSV quotes `"Headset, USB"`; and what
   `float('12,50')` returns (a Compose in a scratch flow). Put the real values in the README; if one differs, fix the
   fake and the tests first, then the narration.
8. **Record the run.** As **Jordan Demo**, upload *Fabrikam price list 2026-12.xlsx* to Price lists. The trigger polls
   (up to 5 minutes). Then record the run, the catalogue and the email.
9. Optional, to film the opening bug for real: *Save as* a copy, turn pagination **off**, turn the original off,
   upload the file again under a new name, and show List price rows with **256** items and "0 rejected" in the email.
   Restore the catalogue afterwards (re-upload it from step 1). Turn the copy off and delete it.
   The row-by-row loop is **not** run in the tenant (794 calls against the throttling budget); it's a code scene
   from `python -m excelfake --row-by-row`.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `library` | `screens/library.jpg` | Price lists library with the uploaded file (Jordan Demo); insert: Excel on the web, table Prices, bottom rows with the four bad rows |
| `run` | `screens/run.jpg` | Run details: all green, Stop not all rows read skipped, List price rows with 400 items and the pagination setting, Upsert catalogue output `result` (15 / 288 / 92 / 1 / 1, bigChanges) |
| `catalogue` | `screens/catalogue.jpg` | Purchasing catalogue.xlsx, table Catalogue: new FAB-0005 price, both FAB-0007 rows, FAB-0381–0395 appended, Valid from as a date, Source column |
| `email` | `screens/email.jpg` | The summary email with the HTML table; insert: the rejected CSV with four rows and Problem |

Code scenes (`read`, `shape`, `comma`, `script`, `loop`, `tests`) come from this folder; terminal output is
recorded locally with `python -m excelfake --row-by-row`, `python -m excelfake` and `python -m pytest`.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Mask the tenant name, site URLs, environment ID, drive IDs (`b!...`) and the script ID in the run's inputs, and
  the mailbox address if it shows a real tenant domain. Only the fictional lab users on screen.
- Excel on the web shows the tenant name in the header: crop or mask.

## Tear-down

- Turn the flow off (and delete the copy from step 9 if made).
- Delete the uploaded price lists and the Rejected CSVs; re-upload the original catalogue if a later episode needs a
  clean one, or keep the updated one.
- Keep the Upsert prices script and the solution for later episodes (ALM in episode 9), or delete the solution.
- Remove the exported zip and the generated workbooks from the recording machine.
