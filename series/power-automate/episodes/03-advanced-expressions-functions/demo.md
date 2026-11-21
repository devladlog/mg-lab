# Demo shot list: DEVLADLOG Power Automate #3, One expression instead of a loop

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant**. Items marked **needs tenant** can't be validated from the build container.

## Prerequisites

| What | Why | Cost |
|---|---|---|
| MG Lab DEV environment with Dataverse (exists) | Solution-aware flow | none |
| Standard licence for the maker (Microsoft 365 or Power Automate) | Recurrence, SharePoint, Outlook and data operations are standard | none |
| SharePoint site `Purchasing` with the `Purchase Requests` list from episode 2 | Data source | none |
| Test users **Alex Demo**, **Jordan Demo**, **Casey Demo**; a `finance-approvers` test mailbox or group | Requesters and recipient | none |
| Power Platform CLI + Python 3 on the recording machine | Export/unpack and re-run tests | none |

No premium connectors, no trials, no Azure resources.

## Setup (≈ 30 min) — **needs tenant**

1. **Data.** In `Purchase Requests`, create items last week (Monday–Sunday, Lisbon time) with these titles, amounts
   and statuses (set Status by hand; turn the episode 2 approval flow **off** first so it doesn't send approvals):
   `[CC-4100] Laptops for two new developers` 12,500 Approved · `[CC-4100] USB-C docking stations` 1,800 Approved ·
   `[cc-2200] Ergonomic chairs for the support team` 4,350.50 Approved · `Conference tickets` 950 Approved ·
   `[CC-3300] Monitor arms` 120 Approved · `[CC-2200] Standing desks` 2,400 Rejected ·
   `[CC-4100] Mechanical keyboard` 89.90 Pending. Created dates are set by SharePoint; the totals in the video will
   be whatever the lab week contains (the dry-run numbers in the script are the sample week's).
2. **Solution** `Purchasing Reports` (unique name `PurchasingReports`, publisher prefix `cts`), add the existing
   connection references for SharePoint and Outlook, then *New → Automation → Cloud flow → Scheduled*
   `Weekly purchasing digest`: weekly, Monday, 07:00, time zone **(UTC+00:00) Dublin, Edinburgh, Lisbon, London**.
   Build it from `src/solution/Workflows/Weeklypurchasingdigest-…301.json`, renaming every action to the JSON names.
   Easiest: add each action, open **Code view** / the expression editor and paste the expression from the JSON.
3. **Check the newer functions.** Confirm the expression editor accepts `slice`, `sort` and `reverse` (they are in
   the functions reference, which says the functions work for Power Automate too). If one is rejected, note it in the
   README and replace: `slice` → `substring` with a guard, `reverse(sort(...))` → keep `sort` and use `last`.
4. **Run it** with *Test → Manually* (or temporarily set the recurrence to run now). Expect: no Apply to each, Total
   and By cost centre with the lab totals, one email to `finance-approvers`.
5. **Confirm the no-offset assumption (1 minute).** Add a temporary Compose with
   `@createArray(ticks('2026-07-06T00:00:00.0000000'), ticks('2026-07-06T00:00:00Z'))`, run, and note whether the two
   numbers are equal (flowkit assumes they are). Delete the Compose. Put the result in the README "not verified" list.
6. **Export and test.**
   ```bash
   pac solution unpack --zipfile PurchasingReports_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   If the designer wrote anything differently (e.g. the list GUID in `table`, extra `metadata`), keep the export and
   adjust the tests, not the other way round.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `list` | `screens/list.jpg` | Purchase Requests with last week's rows: cost-centre prefixes (one lower-case, one missing), Status column with Approved/Rejected/Pending |
| `designer` | `screens/select-designer.jpg` | New designer, `Rows` Select in key/value mode, expression editor open on `costCentre` |
| `run-total` | `screens/run-total.jpg` | Run details, all green, no loop; `Total` output and `By cost centre` output expanded |
| `email` | `screens/digest-email.jpg` | The digest in the finance-approvers mailbox: subject with total, By cost centre and Top three tables |

Code scenes (`window`, `title`, `rows`, `total`, `groupby`, `count`, `gotcha`, `tests`) come from this folder; after
step 6, re-run the commands and update the excerpts if the exported JSON differs.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide the tenant name in URLs, environment IDs and any real user name or address; only the test users on screen.
- Before committing the exported JSON, replace the real site URL with `https://contoso.sharepoint.com/sites/Purchasing`,
  mailboxes with the `contoso.com` ones used in the tests, and any list GUID with the list name or a zero GUID.

## Tear-down

- Turn the digest flow off (or leave the recurrence; it only emails the test mailbox).
- Turn the episode 2 approval flow back on if it's needed later.
- Delete the sample requests if the list is reused for later episodes.
