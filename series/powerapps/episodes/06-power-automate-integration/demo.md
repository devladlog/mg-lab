# Demo shot list — DEVLADLOG Power Apps #6, Power Automate integration

The flow definition, FlowDeploy and the button formulas were tested locally (`dotnet test`: 44 passed; `FlowDeploy --dry-run`
runs without a connection). Everything below **needs the lab tenant** and has not been run there: creating the flow from
`clientdata`, the connections, the app calling the flow, the email.

## Lab environment
No VM and no Azure resource.

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-5 (solution **Equipment Desk**, Loan/Equipment tables, the phone app with the Loans screen) | episode 5's App.Formulas is assumed but not required | existing |
| Recording user: **System Administrator** or **System Customizer** in DEV, **Power Apps Premium** licence, an Exchange Online mailbox (M365 E5 trial) | the licence covers flows run from the Power Apps trigger (Learn FAQ); the owner of a flow with a Dataverse invoker connection needs **Act on behalf of another user** (Learn: Delegate role; System Administrator has it) | existing |
| A second lab test user as the **borrower**, with a mailbox, shown as `alex.demo@contoso.com` on screen | the reminder goes to this mailbox; its address must end with the lab domain the flow allows (see note) | existing licence |
| Azure CLI on the recording laptop (lab Windows host) | only to get a Dataverse token: `az login --allow-no-subscriptions` (off camera), no subscription needed | free |
| .NET 10 SDK on the laptop | `dotnet run` for FlowDeploy | free |

**Domain note:** the flow allows only `@contoso.com` (fictional). In the lab, temporarily change `'@contoso.com'` in the
`Problem` expression of `SendLoanReminder.clientdata.json` to the lab tenant's domain **off camera**, deploy, and never commit
that change or show the real domain (mask it in the run history and Outlook). Alternatively record with a lab user whose
address really ends in contoso.com if such a domain is set up.

All screens are recorded on the **lab Windows host**: terminal, browser on the lab tenant, phone preview.

Things to confirm in the lab and report back (fix code/tests/README if they differ):
- `POST workflows` with this `clientdata` creates the flow and the designer opens it without errors (trigger shows
  **PowerApps (V2)** with input **LoanId**; Respond actions show outputs `sent` (Yes/No) and `message` (Text)).
- `runtimeSource: "invoker"` shows as **Provided by run-only user** in Run only users. If it shows the owner's connection, set it
  there by hand, export the solution (`pac solution export`) and copy the real `clientdata` value back into `src/flow`.
- The app sees the outputs as `result.sent` / `result.message` (lower case, as declared).
- `ThisItem.contoso_loanid` is accepted in Studio (Learn says logical names work; Studio may rewrite it to a display name).
- The Dataverse `GetItem` output has `contoso_duedate` as `yyyy-MM-dd` and the expanded `contoso_EquipmentId` object.
- An Outlook failure body has `error.message` (the send-failed message falls back to "no details" otherwise).

## Steps
1. Off camera: `az login --allow-no-subscriptions`; set `DATAVERSE_URL` and `DATAVERSE_TOKEN` (README). Apply the domain note.
2. From `src/FlowDeploy`: `dotnet run -- ../flow/SendLoanReminder.clientdata.json` → creates the two connection references and
   the flow (off). Record the terminal.
3. make.powerautomate.com → Solutions → **Equipment Desk** → Connection references: open each new reference and pick (or
   create) a **Microsoft Dataverse** and an **Office 365 Outlook** connection for the recording user.
4. `dotnet run -- ../flow/SendLoanReminder.clientdata.json --activate` → "Flow 'SendLoanReminder': on" (`runonly-screen`, part 1).
5. Flow details → **Run only users → Edit**: check both connections are **Provided by run-only user** (`runonly-screen`, part 2).
   Open the flow in the designer and capture `designer-screen`. Don't rename actions (Learn: renaming is a known problem with
   Power Apps triggers).
6. Studio: open **Equipment Desk (phone)** → Power Automate pane → **Add flow** → SendLoanReminder. Replace `btnRemind` with the
   block from `src/app/Src/LoansScreen.pa.yaml` (right-click → Paste code, or paste the formulas). Save and publish.
7. Test data: one loan **overdue** for the borrower test user (e.g. CT-0043, due 16 Nov 2026, not returned) and one **due today**
   or **returned**.
8. Play the app (phone preview), Open loans: tap **Send reminder** on the overdue loan; capture "Sending...", the green banner,
   and the email in the borrower's Outlook on the web (`app-screen`). Then tap it on the not-overdue/returned loan for the yellow
   banner.
9. Flow → 28-day run history: open both runs (`run-screen`).
10. Optional terminal capture for `tests`: `dotnet test FlowTests -m:1` (44 passed).
11. Optional, to show the error path: turn the flow off, tap Send reminder → red "The reminder flow didn't run: ..." banner;
    turn it back on.

### Building it by hand instead (if `POST workflows` is refused)
In the Equipment Desk solution: New → Automation → Cloud flow → Instant → **PowerApps (V2)**. Add a **Text** input named
`LoanId`. Then, without renaming afterwards:

| Action | Settings |
|---|---|
| Dataverse **Get a row by ID** `Get loan` | Table Loans, Row ID = LoanId, Select columns `contoso_name,contoso_borroweremail,contoso_duedate,contoso_returnedon`, Expand Query `contoso_EquipmentId($select=contoso_assettag,contoso_name)` |
| **Compose** `Today` (parallel) | `convertFromUtc(utcNow(), 'GMT Standard Time', 'yyyy-MM-dd')` |
| **Compose** `Problem` | the expression from `clientdata` (runs after Get loan and Today) |
| **Condition** `Can remind` | `outputs('Problem')` is equal to (empty) |
| True: Outlook **Send an email (V2)** `Send reminder`, then two **Respond to a Power App or flow** | outputs `sent` (Yes/No), `message` (Text); `Respond send failed` with Configure run after = has failed / has timed out |
| False: **Respond to a Power App or flow** `Respond skipped` | same outputs |
| **Respond to a Power App or flow** `Respond not found` | Configure run after on Get loan = has failed / has timed out |

Then export the solution and copy the flow's `clientdata` into `src/flow` so the tests run on what the lab really has.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `designer-screen` | `screens/flow-designer.jpg` | Solution Equipment Desk with SendLoanReminder and the two connection references; designer with PowerApps (V2) trigger (LoanId), Get loan, Today, Problem, Can remind (True: Send reminder, Respond sent, Respond send failed; False: Respond skipped), Respond not found |
| `app-screen` | `screens/app-send.jpg` | Phone app Open loans: "Sending..." with other buttons disabled, then green "Reminder sent to alex.demo@contoso.com for CT-0043."; Outlook on the web with "Please return CT-0043 Laptop 14"; second shot yellow "No reminder sent: it isn't overdue yet." |
| `run-screen` | `screens/flow-run.jpg` | Run history with two runs; successful run expanded (Problem empty, True branch, Send reminder and Respond sent succeeded); refused run (Problem "it isn't overdue yet", Respond skipped) |
| `runonly-screen` | `screens/run-only-users.jpg` | Terminal `--activate` output ("... has a connection" twice, "Flow 'SendLoanReminder': on"); Run only users panel with Dataverse and Office 365 Outlook = Provided by run-only user |

## Masking
- Environment name and URL, tenant name and **the real mail domain** (see domain note), user names/avatars, connection names.
- Never show `DATAVERSE_TOKEN`, the `az` output, or connection ids.
- The borrower on screen is the fictional `alex.demo@contoso.com`; mask any real address in run history inputs/outputs.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Keep the flow for later episodes, or turn it off: `PATCH workflows(<id>)` statecode 0 or **Turn off** in the portal. To remove:
   remove it from the app (Power Automate pane → Remove from app), then delete it and the two connection references from the solution.
2. Revert the domain change in `SendLoanReminder.clientdata.json` (`git diff` must show no change in `src/flow`).
3. Delete the reminder emails from the borrower mailbox if they show anything real; reset the test loans.
4. `az logout` on the recording laptop if it was signed in only for this.
