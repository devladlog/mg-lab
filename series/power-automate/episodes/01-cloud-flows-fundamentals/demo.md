# Demo shot list: DEVLADLOG Power Automate #1, Cloud flows fundamentals

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant**. Items marked **needs tenant** can't be validated from the build container.

## Prerequisites

| What | Why | Cost |
|---|---|---|
| MG Lab DEV environment with Dataverse (exists) | Solutions and connection references need Dataverse | none |
| A licence with standard connectors for the maker (Microsoft 365 or Power Automate) | SharePoint, Office 365 Outlook are **standard** connectors | none (existing) |
| SharePoint site `IT Helpdesk` in the lab tenant (create if missing) | List the flows watch | none |
| Two test mailboxes: one for "Alex Demo" (requester), one shared/test box for on-call + service desk | Emails must land somewhere you can film | none |
| Power Platform CLI (`pac`) + Python 3 on the recording machine | Export/unpack and re-run tests | none |

No premium connectors, no trials, no Azure resources.

## Setup (≈ 20 min) — **needs tenant**

1. **List.** In the IT Helpdesk site create list **IT Requests** with columns:
   `Category` (Choice: Hardware, Software, Access), `Priority` (Choice: Low, Normal, High; default Normal),
   `Status` (Choice: New, Triaged, Done; default New), `DueDate` (Date and time, internal name exactly `DueDate`).
2. **Solution.** make.powerautomate.com → DEV environment → *Solutions* → *New solution* `IT Requests`
   (unique name `ITRequests`, publisher prefix `cts` or the lab publisher). Cloud flows must be *created* inside
   the solution to be solution-aware.
3. **Flow 1, automated.** In the solution: *New → Automation → Cloud flow → Automated*, name `IT request intake`,
   trigger SharePoint *When an item is created* (site + list). Then build exactly as in
   `src/solution/Workflows/ITrequestintake-…101.json`:
   - Trigger *Settings → Trigger conditions*: `@not(startsWith(coalesce(triggerBody()?['Title'], ''), '[test]'))`
   - *Initialize variable* `slaHours` (Integer) = `if(equals(triggerBody()?['Priority']?['Value'], 'High'), 4, 24)`
   - *Compose* renamed `Due date` = `addHours(utcNow(), variables('slaHours'))`
   - *Condition* `Is high priority`: Priority Value is equal to `High`; True branch *Send an email (V2)*
     `Alert on-call engineer` (Importance High). Rename actions so the names match the JSON.
   - *Update item* `Mark as triaged` (Id, Title, Status = Triaged, DueDate = output of Due date)
   - *Send an email (V2)* `Acknowledge requester` to Created By Email.
4. **Flow 2, scheduled.** *New → Automation → Cloud flow → Scheduled* `IT requests daily digest`, recurrence
   weekly Mon–Fri at 8:00, time zone (UTC+00:00) Dublin, Edinburgh, Lisbon, London. Then *Get items*
   (`Get open requests`, Filter Query `Status ne 'Done'`, Order By `DueDate asc`, Top Count 500), *Filter array*
   `Overdue requests` (advanced mode: `@less(ticks(coalesce(item()?['DueDate'], '9999-12-31T00:00:00Z')), ticks(utcNow()))`),
   *Condition* `Any open requests` (`length(body('Get_open_requests')?['value'])` greater than 0) →
   *Create HTML table* `Open requests table` (custom columns ID, Title, Priority, Due) → *Send an email (V2)* `Send digest`.
5. **Sample data.** As Alex Demo, add items: "Laptop won't boot before a client demo" (Hardware, **High**),
   "New monitor for the Lisbon office" (Hardware, Normal), "[TEST] please ignore" (Software, Normal).
   Wait 5–10 minutes (polling trigger).
6. **Export and test.** *Solutions → IT Requests → Export → Unmanaged*. Then on the recording machine:
   ```bash
   pac solution unpack --zipfile ITRequests_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   If a test fails, it's a real difference between the designer's JSON and ours (most likely `table` is now the list
   GUID, or action names differ). Fix the test or the flow, commit the exported JSON, note it in the README.
7. Run the digest once with *Test → Manually* so there's a run and an email to film.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `list` | `screens/list.jpg` | IT Requests list view with the three sample items, columns Title, Category, Priority, Status, Due date, Created by |
| `designer` | `screens/designer.jpg` | New designer, `IT request intake` opened from the solution, all six steps visible with the renamed action names |
| `run-high` | `screens/run-high.jpg` | Run details of the High priority run, all green, `Alert on-call engineer` expanded (subject + Importance High); optionally the item showing Triaged + Due date |
| `skipped` | `screens/all-runs-skipped.jpg` | Run history → *All runs* showing a skipped trigger check around the time the `[TEST]` item was created, and no run for it |
| `digest` | `screens/digest.jpg` | The digest email (subject "IT requests: N open, M overdue", HTML table) or the digest run with the Filter array output |

Code scenes (`trigger`, `expressions`, `solution`, `dryrun`, `tests`) come from this folder; re-run the commands
after step 6 and paste real output if it differs.

## Masking

- Run `pipeline/mask.js` in the browser before capturing; `series_label: "POWER AUTOMATE"`.
- Hide the tenant name in URLs (SharePoint site URL, make.powerautomate.com environment ID) and any real user name or
  address. Only contoso-style test users (Alex Demo) on screen.
- The solution JSON committed to Git must not contain the real site URL: replace it with
  `https://contoso.sharepoint.com/sites/ITHelpdesk` (and the list GUID with the list name or a zero GUID) before committing.

## Tear-down

- Turn off both flows (the scheduled one emails every weekday).
- Keep the solution for episode 2 or delete it; delete the `[TEST]` item and sample items if the list is kept.
- Remove the exported zip from the recording machine after unpacking.
