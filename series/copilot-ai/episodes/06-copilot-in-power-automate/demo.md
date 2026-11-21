# Demo shot list - Copilot & AI #6 Copilot in Power Automate

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | The Momento Galático lab tenant, Power Platform environment `DEV`. Note its **region** in the Power Platform admin center: the lab tenant is in Portugal, so Europe is expected. Learn (Power Automate regions and Copilot FAQ): Copilot in cloud flows is available in Europe, and a cross-geo setting decides whether data may leave the geography. Write down the state of that setting before recording and put it back in tear-down |
| Accounts | `labadmin` (the recording account) builds the flow. Work or school account only: Learn says personal accounts are not supported. Fictional borrowers use lab mailboxes, never real people |
| Data | SharePoint site `Contoso Facilities` with a list `Equipment loans` (columns: Title = item, Borrower, BorrowerEmail, DueDate, Status with Out/Returned). Three rows with fictional names (Alex Demo, Sam Demo, Robin Demo) and due dates in the past, so the flow finds something. A Teams team `Contoso Facilities` with channel `General` |
| Licences / purchases | **Nothing bought, cost 0.** Standard connectors only (SharePoint, Outlook, Teams), no premium connector and no Dataverse. Learn lists the licences that cover Copilot in the designer (standalone Power Automate, seeded Microsoft 365, Power Apps or Dynamics 365): confirm on the day that `labadmin` has one of them. **Not recorded, need licences or credits the lab does not have:** Copilot Credits for AI prompts and models used inside flows (usage-based billing; price on the Copilot Studio pricing page, re-read on the recording day) and Copilot Studio agents called from flows. The owner decides whether either is ever bought |
| Azure | none |
| Recording machine | Windows lab laptop: browser on the lab tenant for `make.powerautomate.com`; PowerShell 7 terminal; **Power Platform CLI** (`pac`) installed; **Python 3.10 or later**; this repo cloned. **Never run `pac auth`**: `pac solution unpack` works on a local zip with no sign-in |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Prompt linter PL000 to PL008 (rules taken from the Learn tips page) | yes: pytest | - |
| Expression checker: brackets, quotes, unknown function names (137 names from the Learn function reference), `formatDateTime` pattern letters | yes | - |
| Flow reviewer FR001, FR002, FR003, FR005, FR008, FR009, FR010 on `loan-reminders-draft.json` and `loan-reminders-reviewed.json` | yes: 43 tests in total | - |
| `pac solution unpack` of a zip | yes, offline (used while building) | - |
| Everything Copilot does: create, edit pane, expression assistant, Troubleshoot in Copilot | **no** | **record it** |
| The real flow JSON of a Copilot-built flow, and which findings it really triggers | **no**: the samples are hand-written in the documented shape, they are not Copilot output | **first real run** |
| What `formatDateTime` returns for the expression Copilot writes | **no**: the checker does not evaluate | **run it in Compose** |

Open points to confirm on the tenant, each can change the script:
1. Is **Create with Copilot** available in `DEV` and `labadmin` (region, cross-geo setting, licence)? If not, rewrite the `create-screen` scene around what the tenant really offers.
2. Does the real flow trigger FR001, FR002 and FR005? Copilot may already add a time zone or a Scope. Say what happens, even if the flow is cleaner than the sample.
3. Is the **expression assistant** (preview) shown in the designer in this tenant? What does it return for `Format TriggerDate to 'DD-MM' format` (Learn's own sample prompt)? Keep the real answer.
4. Is **Troubleshoot in Copilot** offered on a failed run in the new designer, and is its suggestion correct?
5. The unpacked folder layout of a cloud flow in a solution (`Workflows/*.json` plus `.data.xml` files): confirm that `flow unpacked` finds the flow. If the file location differs, pass the file path directly.

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, short prompt (`function prompt { 'PS> ' }`). Browser dark theme, 125 %.
- From the episode folder: `python3 -m pytest -q` -> `43 passed`.
- Sample run (no tenant), from `src/`:
  `python3 -m copilot_flow_review flow samples/loan-reminders-draft.json` -> 0 errors, 4 warnings, 1 note;
  `python3 -m copilot_flow_review flow samples/loan-reminders-reviewed.json` -> 0 errors, 0 warnings, 1 note.

## Setup
1. Create the SharePoint list and the three rows, and the Teams channel (see the table). Confirm the connections (SharePoint, Outlook, Teams) once in `Data > Connections`.
2. Admin center: note the region and the cross-geo setting of `DEV`.
3. Rehearse the Copilot prompt off camera once, delete what it created, so the recording starts clean.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `create-flow` - Create with Copilot
`make.powerautomate.com`, environment `DEV`, Home, **Create with Copilot**. Prompt (copy exactly):
`Every weekday at 8:00, get the overdue items from the SharePoint list Equipment loans, email each borrower a reminder with Outlook, then post the number of overdue loans in the Teams channel General.`
Capture the suggestion, **Keep it and continue**, the connections step, **Create flow**, the designer with the Copilot pane.
If the structure is different from what you expected (an extra condition, a different trigger), keep it and say so.
Then **Save**, and add the flow to a solution `Loan reminders` (Solutions, Add existing, Cloud flow).

### 2. `review-draft` - export, unpack, review (terminal)
Export the solution as **unmanaged** to `LoanReminders.zip`. Then:
```powershell
pac solution unpack --zipfile LoanReminders.zip --folder unpacked
python -m copilot_flow_review flow unpacked
```
(run from `src/`, or add the folder to `PYTHONPATH`). Visible: the findings for the real flow, the summary line, exit code. Optional second take: `python -m copilot_flow_review prompt "<your create prompt>"` to show the prompt linter on the real prompt.

### 3. `expression` - expression assistant, then Compose
Add a **Compose** action holding `utcNow()`, then a second Compose. In its field select **fx**, **Create expression with Copilot** and type `Format TriggerDate to 'DD-MM' format` (adapt the name to the real dynamic value). Capture what comes back, **OK**, save and **Test**, open the Compose output. Then in the terminal: `python -m copilot_flow_review expr "<the expression>"`. Show the real output and the checker side by side: whichever is correct, the output is the truth.

### 4. `troubleshoot` - break it, ask Copilot
Make the Teams action fail on purpose (a channel the connection cannot post to, or a wrong list name), **Test**, open the failed run and the red action, select **Troubleshoot in Copilot**. Capture the error and Copilot's answer. Restore the flow afterwards.

## Masking notes
Mask the site URL, the tenant name, the e-mail domain and the environment URL in every capture. Fictional names only (Alex Demo ...). Sign in off camera. Unpacked folders and `LoanReminders.zip` stay local and are never committed: they contain connection reference names and the site URL.

## Tear-down
1. Delete the flow, the solution `Loan reminders` and any run history you do not need.
2. Delete the SharePoint list, the three rows and the Teams channel if you created them for this episode.
3. Put the cross-geo setting back to the state you wrote down.
4. Delete `LoanReminders.zip` and the `unpacked` folder.
5. Nothing else was created: no Azure resources, no purchases.
