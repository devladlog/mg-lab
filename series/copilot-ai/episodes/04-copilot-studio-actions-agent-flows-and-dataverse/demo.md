# Demo shot list - Copilot & AI #4 Copilot Studio: Actions, Agent Flows and Dataverse

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant, Power Platform environment `DEV` (Dataverse, EMEA). Dataverse for Teams environments are **not** supported for agent flows as tools (Learn), so do not use one |
| Accounts | `labadmin` (Global Administrator, **Copilot Studio trial licence**) does everything: table script, flow, agent, test chat. Nobody else is needed |
| Licences / purchases | **Nothing bought. Cost 0.** The trial licence builds and tests but cannot publish (Learn); testing an agent flow from the designer or the agent's test chat does **not** consume Copilot Studio capacity (Learn, *Agent flows overview*). Do **not** publish the agent and do not link a pay-as-you-go plan: the credit slide (`cost` scene) is a calculation from the Learn rates, not something recorded. Published-agent rates used there: agent action 5 Copilot Credits, agent flow actions 13 per 100 actions, pay-as-you-go US$0.01 per credit (series episode 1 has the source). Open point: confirm the trial licence "includes the use of flows in Copilot Studio" (Learn prerequisite for creating agent flows); if the flow designer is blocked, stop and tell the owner what it asks for |
| Azure | none (the token comes from `Connect-AzAccount`, no resource is created) |
| Recording machine | Windows lab laptop: browser as `labadmin`, PowerShell 7 with `Az.Accounts` (`Install-Module Az.Accounts -Scope CurrentUser`), .NET 10 SDK for the test run |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Power Fx rules (`ApprovalTier`, `ValidateRequest`, `ConfirmationMessage`) and the credit estimator | yes: `dotnet test` 27 passed. The formulas run in the open-source Power Fx interpreter (`Microsoft.PowerFx.Interpreter` 1.8.1) with the topic variables as a record named `Topic` | pasting them into the topic and seeing the same result in the test chat |
| `VendorRequest.psm1`: table and column payloads, call order, headers, solution header, `-WhatIf`, error handling, query, token types | yes: Pester, 18 tests, `Invoke-RestMethod` mocked (test only) | **first real run** against `DEV`: the payload shapes follow Learn but were never sent to a live Dataverse |
| Agent flow, tool, topic, MCP server, test chat | no | **record it** |

Open points to confirm on the tenant (each can change a scene or the script):
1. **Autonumber as the primary name column.** Learn describes autonumber columns and the Web API takes `AutoNumberFormat`
   on a string column. Creating the *primary name* column with it in the same `POST /EntityDefinitions` was not verified.
   If Dataverse refuses, create the table without `AutoNumberFormat`, then switch `mgl_requestnumber` to *Autonumber*
   in the maker portal (Learn: a text column can be changed to autonumber) and rewrite the `table-code` scene.
2. **Choice and money in the flow.** In *Add a new row*, Category and Status may need the numeric option value rather
   than the label (values: Hosting 727000000, Printing 727000001, Travel 727000002, Security 727000003, Other 727000004;
   Submitted 727000000, Approved 727000001, Rejected 727000002). The Estimated Annual Cost row may also ask for a
   currency. Record the real configuration and fix the narration.
3. Which wording the agent uses to ask for missing inputs and whether it calls the topic on the first message.
4. That the **Dataverse MCP Server** tool appears in the *Add a tool* list in `DEV` (Learn: enabled by default for
   Copilot Studio; admins can turn it off) and which tool the activity map shows for the count question.
5. Whether the create-agent page offers the standard experience (Learn: turn *New experience* off). Say so on camera if not.

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, short prompt (`function prompt { 'PS> ' }`). Browser dark theme, 125 %.
- `cd series/copilot-ai/episodes/04-copilot-studio-actions-agent-flows-and-dataverse`
- `dotnet test src/PowerFxRules.Tests` -> `Passed: 27`; `pwsh -c 'Invoke-Pester tests/VendorRequest.Tests.ps1'` -> `Passed: 18`.

## Setup
1. **Solution and publisher** (maker portal, make.powerapps.com as `labadmin`, environment `DEV`): Solutions > New
   solution. Display name `MGLab Vendor Desk`, name `MGLabVendorDesk`. Publisher: New publisher, display name `MG Lab`,
   name `mglab`, **prefix `mgl`**, **choice value prefix `72700`** (the script's option values start at 727000000).
2. **Token** (never on camera as text):
   ```powershell
   Connect-AzAccount -Tenant <tenant>.onmicrosoft.com
   $org   = 'https://<org>.crm4.dynamics.com'              # Settings (gear) > Session details > Instance url
   $token = Get-AzAccessToken -ResourceUrl $org -AsSecureString
   Import-Module ./src/scripts/VendorRequest.psm1 -Force
   ```
3. **Table:** `Install-VendorRequestTable -OrgUrl $org -AccessToken $token -SolutionUniqueName MGLabVendorDesk -WhatIf`,
   then without `-WhatIf`. Refresh the solution in the portal: table `Vendor Request` with six columns. In the table's
   forms add the columns you want to see in views (Vendor Name, Category, Estimated Annual Cost, Approval Tier, Status).
4. **Agent:** reuse the *Contoso Vendor Desk* agent from episode 3 if it still exists, otherwise create it as in
   episode 3 (description *Answer Contoso employees' questions about vendor onboarding, payment terms, security
   requirements and renewals. Use only the knowledge sources.*). Settings > Generative AI > **generative orchestration on**.
   The agent must be in `DEV` and, ideally, inside the solution (add it: Solutions > MGLab Vendor Desk > Add existing > Agent).
5. **Agent flow:** Agent > Tools > Add a tool > *Agent flow* (Create new). The starter has the trigger *When an agent calls
   the flow* and *Respond to the agent*. Build:

   | Element | Configuration |
   |---|---|
   | Trigger inputs | `VendorName` (text), `Category` (text), `EstimatedAnnualCost` (number), `Justification` (text), `ApprovalTier` (text). Descriptions written as prompts, e.g. "Name of the vendor, as the user says it" |
   | Add a new row (Microsoft Dataverse) | Table `Vendor Requests`. Vendor Name, Category, Estimated Annual Cost, Justification, Approval Tier from the trigger inputs; Status `Submitted`. Leave Request Number empty (autonumber) |
   | Respond to the agent | Output `RequestNumber` (text) = the Request Number returned by *Add a new row*; settings > Networking > **Asynchronous response Off** |

   Name the flow `Create vendor request`. **Publish.** Connections: sign in as `labadmin` when asked.
6. **Topic** `File a vendor request` (Topics > Add a topic > From blank):
   - Trigger: *The agent chooses*, description: *Use when the user wants to onboard or request a new vendor. Collects
     vendor name, category, estimated yearly cost and justification, files the request and returns the request number
     and the approver. Do not use for policy questions.*
   - Inputs (each with a description as a prompt): `VendorName` text, `Category` text (hosting, printing, travel,
     security or other), `EstimatedAnnualCost` number (euros per year), `Justification` text.
   - Nodes, in order: *Set variable value* `Topic.ValidationError` = formula of `src/PowerFxRules/rules/ValidateRequest.fx`;
     *Condition* `Topic.ValidationError <> ""` -> set output `Answer` to `Topic.ValidationError` and end the topic;
     *Set variable value* `Topic.ApprovalTier` = `ApprovalTier.fx`; *Add a tool* node -> flow `Create vendor request`
     (inputs from the topic variables, output `Topic.RequestNumber`); output `Answer` = `ConfirmationMessage.fx`.
   - Paste each formula in the *Formula* tab of the node (the files contain exactly the text to paste). Learn: formulas
     in Copilot Studio use US number format, commas as separators, variables as `Topic.Name`.
   Test once off camera; write down the wording the agent really uses.
7. **MCP tool:** Add a tool > Model Context Protocol > *Microsoft Dataverse MCP Server* > Add to agent (it asks for a
   Dataverse connection as `labadmin`).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `table-screen` | `screens/table.jpg` | Terminal: the `-WhatIf` run (seven *What if* lines: table plus six columns), then the real run ending `Created mgl_vendorrequest with 6 columns in solution MGLabVendorDesk.` Then the portal: Solutions > MGLab Vendor Desk > Vendor Request > Columns. Mask the org URL |
| `agent-flow` | `screens/agent-flow.jpg` | The flow designer as built in Setup step 5, with the response action's *Settings > Networking > Asynchronous response* **Off** visible, then *Publish* done |
| `topic-screen` | `screens/topic.jpg` | The topic canvas: trigger description, four inputs, the two *Set variable value* nodes with `Topic.ValidationError` and `Topic.ApprovalTier`, the condition, the tool node, the output. One second of *Open code editor* |
| `chat` | `screens/chat.jpg` | Test panel: *We need to onboard Northwind Print for contract printing, about 4,200 euros a year. We print contracts for clients.* Expected: a request number `VR-0001` (or the next one) and approver *Team lead*; the activity map shows the topic and the flow. Keep the real wording |
| `row` | `screens/row.jpg` | Terminal: `Get-VendorRequest -OrgUrl $org -AccessToken $token -Top 3 \| Format-Table` showing the row; then the same row in the portal table view |
| `mcp-screen` | `screens/mcp.jpg` | The Dataverse MCP Server tool in the agent's Tools list, then the test question *How many vendor requests have the status Submitted?* with the real answer |

Extra take (not in the script): ask for `Hosting, 60,000 euros` to show the tier *Finance director, after a security
review*; and ask with an invalid category (*catering*) to show the validation message from Power Fx and that no row is created.

Masking: org URL and tenant in every address bar and in the terminal prompt (`$org` is typed off camera, or pipe
output through `-replace`), email domains, never show `$token`.

## Tear-down
1. In `DEV`: `Remove-VendorRequestTable -OrgUrl $org -AccessToken $token` (confirm; deletes the table **and its rows**).
   Deleting an unmanaged solution does not delete its components, so do this first.
2. Copilot Studio: delete the agent (this removes its topics and tools), delete the flow `Create vendor request`
   (Workflows / Flows page).
3. Maker portal: delete the solution `MGLabVendorDesk` and, if nothing else uses it, the publisher `mglab`.
4. `Disconnect-AzAccount`; close the browser profile.
