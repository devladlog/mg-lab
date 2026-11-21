# Demo shot list: DEVLADLOG Power Automate #12, AI Builder document processing

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none (the Hyper-V lab on 10.50.0.0/24 is not used) |
| Power Platform | Environment **`DEV`** (Dataverse). **It must be a Production or Sandbox environment**: Learn says pay-as-you-go is available for those types only (not Trial or Developer). Check the type in the Power Platform admin center (PPAC) before anything else |
| SharePoint | New site `Finance` (or a library and two lists on `IT Helpdesk`). Library **Invoice Inbox**; lists **Invoice Extractions** and **Invoices** (columns below) |
| Lab users | `labadmin` (Global Administrator): billing plan, PPAC, Azure. `alex.demo` (Alex Demo): builds and runs the flows, Environment Maker in DEV, member of the Finance site. `sam.demo`: the reviewer, receives the review emails (set as the value of `cts_ReviewerMailbox`; never write the address into the repo) |
| Licences | The flows use the **AI Builder** action, so they are premium: start the self-service **Power Automate Premium trial** for `alex.demo` (LAB.md). **AI Builder capacity is separate**: AI Builder credits are being phased out (Learn: End of AI Builder credits), so don't count on a trial or seeded credits; the environment needs **Copilot Credits**: a **pay-as-you-go billing plan** linked to DEV (setup below). Cost: 8 Copilot Credits per page = $0.08 (Learn rate table, pay-as-you-go $0.01 per credit); the whole demo is about 10 pages, under $1 |
| Azure | Resource group **`rg-mglab-pa-12`** in the lab subscription, created in the Azure portal by `labadmin`, with a budget alert (the lab budget is €30 per month). No other Azure resource: the billing plan creates one hidden *Power Platform account* resource inside it |
| Recording machine | The Windows lab laptop with the browser and `pipeline/mask.js`; a terminal with Python 3.10+ and `pac` for the `invoicekit` captures. The files in `src/samples/` are copied to the laptop for upload |

Everything in `src/` and `tests/` runs without the tenant (see README). **Needs tenant**: everything on this page.

## Setup (≈ 60 min) **needs tenant**

1. **Azure budget, off camera.** Azure portal as `labadmin`: create resource group `rg-mglab-pa-12`; Cost Management → Budgets on that group: €30 per month, alert at 80 percent to the lab admin. (No `az login` from the repo or the agent; it is a manual portal step.)
2. **Billing plan.** PPAC → **Licensing → Pay-as-you-go plans → New billing plan → Azure subscription** (Learn, *Set up pay-as-you-go*): name `mglab-pa-12`, the lab subscription, resource group `rg-mglab-pa-12`, the Power Platform product for which the meters apply (the dropdown is where Learn is least specific: choose the one that covers AI Builder / Copilot Credits in Power Automate; if it isn't clear, look at what the list offers and note it in the README), then **select DEV** and **Save**. The record shown on the `cost` screen is this page.
3. **Site and lists** (as `alex.demo`, SharePoint):
   - Library **Invoice Inbox** (default columns).
   - List **Invoice Extractions**: `Title` (default, unused), single-line text `InvoiceId`, `VendorName`, `PurchaseOrder`, `SourceFile`; date-only `InvoiceDate`, `DueDate`; number (2 decimals) `SubTotal`, `TotalTax`, `InvoiceTotal`; number (0 to 1, 2 decimals) `InvoiceIdConf`, `VendorNameConf`, `InvoiceDateConf`, `DueDateConf`, `SubTotalConf`, `TotalTaxConf`, `InvoiceTotalConf`; choice `Decision` with `auto-post`, `review`, `reject`. **Use these internal names exactly** (create each column with a name without spaces, then rename the display name if you like): the flow reads them by internal name.
   - List **Invoices**: `Title`, single-line text `InvoiceId`, `VendorName`, date-only `InvoiceDate`, number `InvoiceTotal`.
4. **Import the triage flow.** Pack the repo solution and import it into DEV as `alex.demo` (the demo shows the import, so do this on camera or screen-record it):
   ```bash
   cd src
   pac solution pack --zipfile ../out/ITInvoiceIntake.zip --folder solution --packagetype Unmanaged
   # sign in (pac auth create ...) off camera, then
   pac solution import --path ../out/ITInvoiceIntake.zip
   ```
   Set the connection references (SharePoint, Outlook) and the environment variables: `Finance site URL` (the real site), `Reviewer mailbox` (sam.demo), leave the thresholds at 0.8, 5000 and 365. **If the import fails or the flow doesn't turn on, the files we wrote are wrong (see README, "not verified"): build the same flow in the designer instead and export it, then replace `src/solution/` with the real export and rerun the tests.**
5. **Build the extraction flow in the designer** (it is deliberately *not* in the repo, see README), in the same solution or a new one named `IT Invoice Extraction`, prefix `cts`:
   1. Trigger: SharePoint **When a file is created (properties only)**, site Finance, library Invoice Inbox.
   2. **Get file content** (SharePoint) with the file identifier from the trigger.
   3. AI Builder **Extract information from invoices** (Learn: *Use the invoice processing prebuilt model in Power Automate*): *Invoice file* = file content; leave *Pages* empty for now.
   4. **Create item** in Invoice Extractions. Map: `InvoiceId` = *Invoice ID*; `VendorName` = *Vendor name*; `PurchaseOrder` = *Purchase order*; `InvoiceDate` = *Invoice date (date)*; `DueDate` = *Due date (date)*; `SubTotal` = *Subtotal (number)*; `TotalTax` = *Total tax (number)*; `InvoiceTotal` = *Invoice total (number)*; each `...Conf` = the matching *Confidence of ...* output; `SourceFile` = the file name. Use the **(number)** and **(date)** outputs, never the **(text)** ones: the triage rules compare numbers and dates.
   5. Save and turn it on. If a connector or action prompts for credits or an AI Builder error appears (`EntitlementNotAvailable` / `QuotaExceeded` per Learn), the environment has no capacity: re-check step 2.
6. Optionally export the extraction flow's solution with `pac solution export` + `unpack` and keep the **flow JSON** (after masking): it tells us the real operation id and output names (README, "not verified").

## Recording flow and screens (match the `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `extract` | `screens/extract.jpg` | The extraction flow in the designer, all four actions open enough to read: trigger, Get file content, **Extract information from invoices** (Invoice file, Pages), Create item with the mapped fields. Mask tenant name, site address, address bar |
| `extractions` | `screens/extractions.jpg` | Drop in the Invoice Inbox, one by one: `invoice-clean.pdf`, `invoice-scan.png`, `invoice-mismatch.pdf`. Then the Invoice Extractions list view showing InvoiceId, VendorName, InvoiceTotal and the three or four confidence columns side by side. Record **whatever the model returns** for the scan (if the synthetic scan comes back empty, replace it with a photo or a print-and-scan of `invoice-clean.pdf` and say so in the narration; do not edit values) |
| `decision` | `screens/decision.jpg` | (1) The Decision column filled by the triage flow. (2) The Invoices list with the posted row. (3) The Outlook message to `sam.demo` for the mismatch (the flow's *Ask_reviewer* email). (4) Drop `invoice-clean.pdf` a second time: `Decision = reject`. To also show OVERLIMIT: set the environment variable `Amount limit` to 500 for one run (clean invoice total is 747.60) and set it back |
| `cost` | `screens/cost.jpg` | Power Automate → **Automation Center → Monitor → AI Builder activity** (Learn: *Monitor AI Builder models and prompts activity*) with the predicts of this session and their Consumption column; then the PPAC billing plan page. Mask the tenant, subscription name and subscription ID |

Code scenes are terminal captures from `src/`: `preflight` (`python -m invoicekit preflight samples/*`), `triage` (`python -m invoicekit triage extractions/*.json --today 2026-11-10`; the rows are mocks, which the narration says), `rules` and `flow` (the file excerpts). **Also show once, on camera, the Pages parameter**: in the AI Builder action set *Pages* to `2-3`, run the flow once with `invoice-two-in-one.pdf` and show that the extracted invoice is `INV-2026-0413` (the value comes from the real model; if it returns something else, tell the truth in the narration and fix README).

## What to check after recording (and fix the README and script if it differs)

- **Which column names the real action outputs have**, the exact operation id in the exported flow JSON, and whether the confidence outputs are plain numbers between 0 and 1.
- **Whether the triage flow turns on from the import** and triggers on the rows the extraction flow creates (the trigger polls: expect up to a minute).
- **The actual confidence values** for the three samples: if the clean PDF scores below 0.8 on a required field, the narration of `extractions` and the README example are wrong; adjust the narration, not the data.
- That the **Pages = `2-3`** run returns invoice `INV-2026-0413` and only its lines.
- That the **consumption** on the AI Builder activity page is 8 credits per page (Learn rate table) and that nothing was billed for testing in the AI hub (Learn: testing prebuilt models consumes no credits).
- That **duplicate detection** needs the first invoice to be in the *Invoices* list: yes, the flow queries it, not the staging list.
- Whether the **Learn pages that disagree** about AI Builder in flows being premium (*Overview of licensing*: premium; *Licensing and AI Builder credits*: not) matter for what you saw in the maker portal (a premium badge on the action).

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide: tenant name, site URLs, mailbox domains, subscription name and ID, resource group IDs, user principal names. The sample invoices are fictional (Adatum Office Supplies, Contoso Ltd), no masking needed on them.

## Tear-down (same day)

1. PPAC → Licensing → Pay-as-you-go plans: **remove DEV from the billing plan**, then delete the plan (Learn: *Turn off pay-as-you-go*). Delete resource group `rg-mglab-pa-12` in the Azure portal (this deletes the hidden Power Platform account resource). Check Cost Management for the day's charge and note it in the README.
2. Delete the flows and solutions in DEV, the lists, the library and the site `Finance`.
3. Let the Power Automate Premium trial expire; do not extend it.
4. Delete `out/` and the `pac` auth profile (`pac auth clear`).
