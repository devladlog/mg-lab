# DEVLADLOG Power Apps #6 — Power Automate integration: the app asks, the flow checks and sends

Episode 3's **Copy reminder** button put a reminder text on the clipboard and left the rest to the user. This episode
replaces it with **Send reminder**: the phone app calls a cloud flow, **SendLoanReminder**, which reads the loan from
Dataverse, decides whether a reminder is allowed, sends the email with Office 365 Outlook and **answers the app** with
`sent` and `message`. The app only shows what the flow says.

The design follows Learn's warning in the Power Automate pane article: arguments passed from Power Apps "are visible as
network traffic and can be intercepted", so validate them in the flow. The app sends **only the loan id**; recipient,
device and due date come from Dataverse, and the flow refuses returned loans, loans that aren't overdue yet (in Lisbon
time) and borrowers outside `contoso.com`. Every path ends in exactly one **Respond to a Power App or flow**.

The flow is kept as **code**: `clientdata` (connection references + workflow definition) in `src/flow`, deployed into the
episode 1 solution with **FlowDeploy**, a small .NET console that uses the Dataverse Web API exactly as Learn's
"Work with cloud flows using code" describes.

| Path | What it is |
|---|---|
| [`src/flow/SendLoanReminder.clientdata.json`](src/flow/SendLoanReminder.clientdata.json) | The flow: Power Apps (V2) trigger with one input (`LoanId`), Dataverse **Get a row by ID** (`GetItem`, with `$select`/`$expand`), `Today` in Lisbon (`convertFromUtc`), a `Problem` check, Outlook **Send an email (V2)** (`SendEmailV2`), four **Respond** actions with identical outputs |
| [`src/FlowDeploy`](src/FlowDeploy) | Console: creates connection references (if missing) and the workflow row in solution **EquipmentDesk** (`MSCRM.SolutionUniqueName`), updates `clientdata` on re-runs, turns the flow on only when every reference has a connection; `--dry-run` sends nothing |
| [`src/app/Src/LoansScreen.pa.yaml`](src/app/Src/LoansScreen.pa.yaml) | Episode 3's Loans screen; `btnRemind` now calls `SendLoanReminder.Run(...)`, disables the reminder buttons while the flow runs, and shows the flow's message |
| [`tests/FlowTests`](tests/FlowTests) | 44 xUnit tests |
| [`tests/FlowTests/Wdl`](tests/FlowTests/Wdl) | A small interpreter for the workflow definition language subset this flow uses (functions per Learn's expression reference, `runAfter`, `If`, `Compose`, `Response`, connector calls answered by fakes) |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test FlowTests -m:1
# Passed!  - Failed: 0, Passed: 44, Skipped: 0, Total: 44 (.NET 8, Microsoft.PowerFx.Connectors/Interpreter 1.8.1)

cd ../src/FlowDeploy
dotnet run -- ../flow/SendLoanReminder.clientdata.json --dry-run --activate
# Plan for 'SendLoanReminder' in solution EquipmentDesk (dry run, nothing sent):
#   connection reference contoso_EquipmentDeskDataverse -> /providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps (create if missing)
#   connection reference contoso_EquipmentDeskOutlook -> /providers/Microsoft.PowerApps/apis/shared_office365 (create if missing)
#   workflow 'SendLoanReminder': create (category 5, type 1, primaryentity none) or update clientdata (5551 chars)
#   then turn it on (statecode 1) if every connection reference has a connection
```

What the four groups prove:
- **FlowRunTests** (21 cases): the real definition, run path by path: an overdue loan gets one email (to, subject, body with
  "Monday 16 November 2026") and `sent: true`; returned, due today and external borrower get a reason and no email; an
  upper-case address still passes (Learn: `endsWith` isn't case-sensitive); unreadable, missing or tampered ids and a
  Dataverse timeout get "couldn't be read"; an Outlook failure is reported; **overdue is decided in Lisbon time**
  (23:30 UTC on 14 July is already the 15th there); every path answers the app exactly once.
- **FlowDefinitionTests** (9): the `clientdata` shape from Learn; trigger kind `PowerAppV2` with one typed required input;
  nothing from `triggerBody()` reaches the email; every connector action has a connection reference and vice versa; every
  `runAfter` is valid; every expression parses, uses known functions and names real actions; every Respond action has the
  same two outputs; only documented operation ids (`GetItem`, `SendEmailV2`).
- **AppContractTests** (6): the button's formulas from `LoansScreen.pa.yaml` on the Power Fx interpreter, calling a
  stand-in `SendLoanReminder.Run` built from the flow's own trigger and response schemas that runs the real definition:
  success and warning notifications show the flow's message, a disabled flow shows an error, the buttons come back.
- **DeployTests** (8): FlowDeploy against an in-memory Web API: dry run sends nothing; first deploy creates two connection
  references and the workflow (category 5, type 1, `primaryentity` none) in the solution and leaves it off; `clientdata` is a
  JSON **string** equal to the file; `--activate` refuses until connections are picked; re-deploying an active flow turns it
  off, updates it and turns it back on; Dataverse errors are shown.

What they **don't** prove: that Power Automate accepts this exact definition (the action and trigger shapes are the ones
Learn documents and the designer writes, but only the lab import proves it), how Power Apps itself hosts a flow call,
real Outlook or Dataverse behaviour, or the 120-second limit. That's the lab run in [`demo.md`](demo.md).

## Deploy it in the lab (needs tenant)

```bash
export DATAVERSE_URL=https://<dev-org>.crm4.dynamics.com
export DATAVERSE_TOKEN=$(az account get-access-token --resource $DATAVERSE_URL --query accessToken -o tsv)   # az login --allow-no-subscriptions
cd src/FlowDeploy
dotnet run -- ../flow/SendLoanReminder.clientdata.json            # creates references + flow (off)
# maker portal > Solutions > Equipment Desk > Connection references: pick a Dataverse and an Office 365 Outlook connection
dotnet run -- ../flow/SendLoanReminder.clientdata.json --activate # turns it on
```

Then in the flow's details: **Run only users → Edit** and check that both connections are **Provided by run-only user**.
In Studio: **Power Automate pane → Add flow → SendLoanReminder**, then paste `btnRemind` from `LoansScreen.pa.yaml`.
The same flow can be built by hand in the designer from the table in [`demo.md`](demo.md). This has **not yet run against
the lab tenant**.

## What we learned / gotchas

- **Validate in the flow, not in the app.** Learn: arguments from Power Apps "can be intercepted"; check them in Power Automate
  (their example: allow only `@contoso.com`). Our trigger takes a row id and nothing else, so the app can't choose the recipient
  or the text, and a tampered id just fails the Dataverse read (test `A_loan_the_user_cannot_read_is_a_polite_no_not_a_failed_run`).
- **Whose connection runs the flow?** Learn (share a cloud flow): a connection set to **Provided by run-only user** uses the person
  who taps the button; an **embedded** connection uses the account behind it, "which might have access to data that app users can't
  access directly". We use the invoker for both (`runtimeSource: invoker`): the flow can only read loans the user can read, and the
  email comes from the user. Saving a Dataverse action with invoker connections needs the **Act on behalf of another user** privilege
  (Learn: Delegate role) for the flow owner.
- **Every path must respond, and within 120 seconds.** Learn: a synchronous call from an app fails with `ResponseTimeout` after
  120 seconds; a flow with a Respond action returns within that limit, and actions after the response keep running. A path that
  never reaches a Respond action leaves the app waiting, so the Dataverse failure and timeout get their own Respond action (test
  `Every_path_answers_the_app_exactly_once`).
- **Same outputs on every Respond action.** Learn (troubleshooting): Power Apps stores the flow's inputs, connections and outputs in
  the app; removing an output is a breaking change and a removed output reads as blank. All four Respond actions declare `sent`
  and `message`.
- **Change the flow, then refresh it in the app.** Learn: after editing a flow outside Studio, refresh it in the Power Automate pane
  "otherwise, the flow may fail to run, even in previously published apps". Adding an input or a connection breaks published app
  versions; Learn's advice for a live app is to **Save As** a copy of the flow and switch the app to it.
- **"Today" needs a time zone.** `utcNow()` is UTC; a loan due on 14 July is overdue at 00:30 on the 15th in Lisbon but not yet in
  UTC. `convertFromUtc(utcNow(), 'GMT Standard Time', 'yyyy-MM-dd')` (Learn: Windows time zone names) fixes the boundary.
- **`endsWith` ignores case** (Learn), so `Jordan.Demo@CONTOSO.COM` passes the domain check without `toLower`.
- **Dates come back as `yyyy-MM-dd` text.** We compare them as strings after `formatDateTime(..., 'yyyy-MM-dd')`; Learn's `less`
  accepts strings.
- **Rename actions before adding the Power Apps trigger.** Learn (trigger troubleshooting) lists "Unable to rename actions in a cloud
  flow" with Power Apps triggers; the workaround is remove trigger, rename, re-add. Keeping the definition as code avoids it.
- **Flows from code must be in a solution.** Learn: managing flows under **My flows** with code isn't supported; the `workflow` row
  (category 5) is created off, and `clientdata` is a **string** column holding JSON. FlowDeploy adds it to the solution with the
  `MSCRM.SolutionUniqueName` header (Learn: optional parameters, works on create and update).
- **Use the logical name for the row id.** Episode 1 named both the Loan primary key and its primary name column "Loan", so the button
  uses `ThisItem.contoso_loanid` (Learn: logical names work in formulas even though Studio doesn't suggest them).
- **Licensing.** Learn: a Power Apps per user (Premium) licence covers flows "executed through a Power Apps trigger action"; the app is
  premium anyway because of Dataverse.
- **The test interpreter is ours.** `Wdl/` implements only the functions this flow uses, with Learn's documented behaviour, and throws
  on anything else; it is not Logic Apps. We checked it bites: changing `convertFromUtc` to `utcNow`, the domain or one Respond
  schema fails 7 tests.

## References
- [Use the Power Automate pane in Power Apps Studio (add, refresh, security note)](https://learn.microsoft.com/power-apps/maker/canvas-apps/working-with-flows)
- [Troubleshoot Power Apps flow integration issues (breaking changes, ResponseTimeout)](https://learn.microsoft.com/troubleshoot/power-platform/power-apps/connections/best-practices-when-updating-a-flow)
- [Known issues with Power Apps V2 trigger (embedded and invoker connections)](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-creation/known-issues-power-apps-v2-trigger)
- [Troubleshoot Power Automate trigger problems (Power Apps trigger, renaming actions)](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot)
- [Limits of automated, scheduled, and instant flows (120-second inbound request)](https://learn.microsoft.com/power-automate/limits-and-config#request-limits)
- [Share a cloud flow (run-only users, flows used by canvas apps)](https://learn.microsoft.com/power-automate/create-team-flows#share-a-cloud-flow-with-run-only-permissions)
- [Manage connections for the Microsoft Dataverse connector (Act on behalf of another user)](https://learn.microsoft.com/power-automate/dataverse/manage-dataverse-connections)
- [Work with cloud flows using code (workflow table, clientdata, create, update)](https://learn.microsoft.com/power-automate/manage-flows-with-code)
- [Use optional parameters: associate a solution component with a solution](https://learn.microsoft.com/power-apps/developer/data-platform/optional-parameters#associate-a-solution-component-with-a-solution)
- [Connection Reference (connectionreference) table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/connectionreference)
- [Reference guide to workflow expression functions (convertFromUtc, endsWith, less, formatDateTime)](https://learn.microsoft.com/azure/logic-apps/expression-functions-reference)
- [Microsoft Dataverse connector reference (GetItem)](https://learn.microsoft.com/connectors/commondataserviceforapps/)
- [Office 365 Outlook connector reference (SendEmailV2)](https://learn.microsoft.com/connectors/office365/)
- [Operators and identifiers: display names and logical names](https://learn.microsoft.com/power-platform/power-fx/reference/operators#display-names-and-logical-names)
- [Power Apps licensing FAQs (Power Apps licence and Power Apps-triggered flows)](https://learn.microsoft.com/power-platform/admin/powerapps-licensing-faq)
- Blog: [Power Automate Integration — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-25-power-automate-integration-complete-guide-2026/)
