# DEVLADLOG Copilot & AI #4 - Copilot Studio: Actions, Agent Flows and Dataverse

Episode 3 gave the **Contoso Vendor Desk** agent knowledge. This episode lets it **act**: file a vendor request that
lands as a row in Dataverse, with the approver decided by a rule that is tested, not guessed by a model.

The split of work (Learn: *keep deterministic logic and guardrails inside the topic*):

| Who | Does what | Where in this folder |
|---|---|---|
| Language model | Understands "we need to onboard Northwind Print...", asks for the missing values | agent + topic inputs (portal) |
| Power Fx in the topic | Validates the input, picks the approval tier (same thresholds as the policy of episode 3), builds the confirmation text | [`src/PowerFxRules/rules/*.fx`](src/PowerFxRules/rules), tested |
| Agent flow (tool node) | Writes the row, returns the request number | built in the portal, spec in `demo.md` |
| Dataverse | Table, autonumber request number (`VR-0001`), choices, security | [`src/scripts/VendorRequest.psm1`](src/scripts/VendorRequest.psm1), tested |
| You, before publishing | Credit estimate per request | [`src/PowerFxRules/CreditEstimator.cs`](src/PowerFxRules/CreditEstimator.cs), tested |

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous: episode 3,
[Your first agent with SharePoint knowledge](../03-copilot-studio-your-first-agent-with-sharepoint-kn/) (same agent and
policy). Next: episode 5, *Copilot in Power Apps*. Category episodes this builds on:
[Dataverse deep dive](../../../dynamics-365/episodes/01-dataverse-deep-dive/) (table as code with the Web API, in Python),
[Dataverse integration in Power Apps](../../../powerapps/episodes/04-dataverse-integration/),
[Power Automate error handling](../../../../episodes/02-power-automate-error-handling/) and
[Dataverse vs SharePoint](../../../../episodes/03-dataverse-vs-sharepoint/).

| Path | What it is |
|---|---|
| [`src/PowerFxRules/rules/ApprovalTier.fx`](src/PowerFxRules/rules/ApprovalTier.fx) | Team lead below 5,000 euros a year, procurement manager from 5,000, finance director after a security review from 25,000 |
| [`src/PowerFxRules/rules/ValidateRequest.fx`](src/PowerFxRules/rules/ValidateRequest.fx) | Returns the first problem as text, or empty text when the request is valid |
| [`src/PowerFxRules/rules/ConfirmationMessage.fx`](src/PowerFxRules/rules/ConfirmationMessage.fx) | `Request VR-0007 for Northwind Print (4,200 EUR a year) is waiting for: Team lead.` |
| [`src/PowerFxRules/RuleEngine.cs`](src/PowerFxRules/RuleEngine.cs) | Evaluates a `.fx` file with the open-source Power Fx interpreter; topic variables are a record called `Topic` |
| [`src/PowerFxRules/CreditEstimator.cs`](src/PowerFxRules/CreditEstimator.cs) | Copilot Credits with the rates of the Learn billing page |
| [`src/PowerFxRules.Tests/RuleTests.cs`](src/PowerFxRules.Tests/RuleTests.cs) | 27 xUnit tests (boundaries, validation order, US number format, the three worked examples of Learn) |
| [`src/scripts/VendorRequest.psm1`](src/scripts/VendorRequest.psm1) | `Install-VendorRequestTable`, `Get-VendorRequest`, `Remove-VendorRequestTable` and the table and column payloads |
| [`tests/VendorRequest.Tests.ps1`](tests/VendorRequest.Tests.ps1) | 18 Pester tests, `Invoke-RestMethod` mocked |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 790 words) and shot list with the exact flow, topic and table setup |

## Run and test

```bash
cd series/copilot-ai/episodes/04-copilot-studio-actions-agent-flows-and-dataverse
dotnet test src/PowerFxRules.Tests -m:1        # Passed: 27 (restores Microsoft.PowerFx.Core and .Interpreter 1.8.1 from nuget.org)
pwsh -NoProfile -Command 'Invoke-Pester tests/VendorRequest.Tests.ps1'   # Tests Passed: 18
```

Against the tenant (needs the tenant; see `demo.md` for the solution, publisher and flow setup):

```powershell
Connect-AzAccount -Tenant <tenant>.onmicrosoft.com
$org   = 'https://<org>.crm4.dynamics.com'
$token = Get-AzAccessToken -ResourceUrl $org -AsSecureString
Import-Module ./src/scripts/VendorRequest.psm1 -Force
Install-VendorRequestTable -OrgUrl $org -AccessToken $token -SolutionUniqueName MGLabVendorDesk -WhatIf
Install-VendorRequestTable -OrgUrl $org -AccessToken $token -SolutionUniqueName MGLabVendorDesk
Get-VendorRequest -OrgUrl $org -AccessToken $token -Top 3 | Format-Table
```

Verified here: `dotnet test` 27 passed (.NET 10, Power Fx 1.8.1), Pester 18 passed (PowerShell 7.6, Pester 6.2).
**Not verified without the tenant:** the table and column payloads against a live Dataverse (in particular an
autonumber as the *primary name* column of a new table, see `demo.md` open point 1), and everything built in
Copilot Studio: the agent flow, the topic, the Dataverse MCP server tool and the test chat. The agent flow and the topic
are described step by step in `demo.md`, not exported, because a flow and a topic cannot be validated outside the product.

## What we learned / gotchas

All from Microsoft Learn (checked 21 Nov 2026), except where marked.

- **Names moved.** In the standard harness the old "actions" are **tools**; a Power Automate flow built for an agent is an
  **agent flow**. Learn also describes two newer harnesses (Microsoft Copilot, Customer Conversation) where the same
  idea is a *workflow*. This episode follows the standard harness (create the agent with *New experience* off).
- **A flow can be a tool only if** it has the **When an agent calls the flow** trigger and a **Respond to the agent**
  action, is **published**, has **Asynchronous response off** (Respond to the agent > Settings > Networking) and answers
  within the **100-second** action limit. Longer work goes after the respond action. Agent flows need a Dataverse
  environment: **Dataverse for Teams is not supported**. An existing cloud flow can be converted to an agent flow, but
  conversion is one-way because the billing changes (it must be in a solution).
- **Credentials.** In a supported authenticated agent a flow can run with the user's credentials (run-only user); in
  environments with customer-managed keys it cannot yet, set specific connections instead.
- **Topic best practice (standard harness):** a clear name and a description that says when to use the topic; one input
  per value with a description written as a prompt to the orchestrator; inputs named for the value (the name becomes the
  question); deterministic logic and guardrails (entities, validation, Power Fx) inside the topic; avoid messaging the
  user from inside the topic, return outputs. Names carry more weight than descriptions, and overlapping descriptions
  make the choice unpredictable.
- **Power Fx in Copilot Studio:** variables carry a scope prefix (`Topic.`, `Global.`, `System.`, `Environment.`), numbers
  are US style (comma as parameter separator), and the **Choice** type is *not supported* as a literal, which is why the
  flow takes the category as text. The rules here use only `If`, `Or`, `Not`, `Lower`, `Len`, `IsBlank`, `Text` and
  `Proper`, all in Learn's list for Copilot Studio (the `&` operator is core Power Fx, not on that list).
- **Autonumber columns (Dataverse):** format `VR-{SEQNUM:4}`; the sequence number has a *minimum* length and keeps growing
  (so do not set `MaxLength` to the formatted length); `{RANDSTRING}` is limited to 6 characters; the placeholders are not
  validated until the first save; a started-then-cancelled row burns its number, so gaps are normal; the column's format
  must be Text; an existing text column can be switched to autonumber.
- **Web API:** labels set only `LocalizedLabels`; `MSCRM.SolutionUniqueName` puts the new table and columns into the
  solution; the money column takes its precision from the record currency (`PrecisionSource` 2). `Get-VendorRequest` asks
  for formatted values (`Prefer: odata.include-annotations`) to get choice labels, and refuses request numbers that are
  not `VR-0000` shaped so nothing can be injected into the `$filter`.
- **Token:** Learn's documented way without your own app registration: `Connect-AzAccount`, then `Get-AzAccessToken
  -ResourceUrl <org> -AsSecureString` (the default output of the token cmdlet is now a SecureString; the module accepts
  a string, a SecureString or the token object).
- **Credits (standard harness, published agents).** Classic answer 1, generative answer 2, agent action 5, tenant graph
  grounding 10, **agent flow actions 13 per 100 actions**; each agent-flow trigger execution is billed like one action.
  Testing in the designer or in the test chat is not billed. When an environment has **no credits**, new agent flow runs
  are blocked while the agent itself keeps answering; the test chat and designer test runs are not affected. Runs started
  by the agent with the *When an agent calls the flow* trigger under a user who holds a Microsoft 365 Copilot licence
  are not charged. `CreditEstimator.OneVendorRequest` assumes **1 agent action + 3 flow actions** = 5.39 credits (US$0.054
  at US$0.01 per credit, see series episode 1). Learn words the rule in two ways (generative orchestration: one agent
  action plus the flow actions; from a topic: one classic answer plus the flow actions), so treat the number as an estimate
  and read the real one in the Power Platform admin center, *Licensing > Copilot Studio*, after a run.
- **Dataverse MCP server:** enabled for Copilot Studio by default in every environment (an admin can turn it off; other
  clients such as GitHub Copilot must be allowed). Tool names changed: `search_data`, `search` (metadata), `read_query`,
  `describe`, `create_record`, `update_record`, `invoke_api` and others; old names `list_tables`, `describe_table` and
  `fetch` were removed. `search_data` is billed on usage-based Copilot Credits, the other tools at the *basic text and
  generative AI tools* rate. Use it for reading; keep an agent flow for writes you want to control.

## References

Microsoft Learn
- [Agent flows overview](https://learn.microsoft.com/microsoft-copilot-studio/flows-overview)
- [Create an agent flow as a tool](https://learn.microsoft.com/microsoft-copilot-studio/advanced-flow-create)
- [Add an agent flow as a tool to an agent](https://learn.microsoft.com/microsoft-copilot-studio/flow-agent)
- [Call an agent flow from an agent](https://learn.microsoft.com/microsoft-copilot-studio/advanced-use-flow)
- [Asynchronous response support for agent flows](https://learn.microsoft.com/microsoft-copilot-studio/flow-asynchronous-response)
- [Design topics as mini-agents that avoid duplicate messages](https://learn.microsoft.com/microsoft-copilot-studio/guidance/generative-orchestration-topics)
- [Orchestrate agent behavior with generative AI (descriptions)](https://learn.microsoft.com/microsoft-copilot-studio/advanced-generative-actions)
- [Apply generative orchestration capabilities](https://learn.microsoft.com/microsoft-copilot-studio/guidance/generative-orchestration)
- [Create expressions using Power Fx](https://learn.microsoft.com/microsoft-copilot-studio/advanced-power-fx)
- [Billing rates and management (Copilot Credits, agent flow enforcement)](https://learn.microsoft.com/microsoft-copilot-studio/requirements-messages-management)
- [FAQ for Copilot Studio billing and licensing](https://learn.microsoft.com/microsoft-copilot-studio/faq-billing-licensing)
- [Connect to Dataverse with Model Context Protocol (tool list, billing)](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp)
- [Connect to Dataverse with MCP in Copilot Studio](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-copilot-studio)
- [Configure and manage the Dataverse MCP server for an environment](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-disable)
- [Create autonumber columns](https://learn.microsoft.com/power-apps/developer/data-platform/create-auto-number-attributes)
- [Create and update table definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-definitions-using-web-api)
- [Create and update column definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-column-definitions-using-web-api)
- [Authenticate to Microsoft Dataverse with the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/authenticate-web-api)
- [Get-AzAccessToken](https://learn.microsoft.com/powershell/module/az.accounts/get-azaccesstoken)

Other official documentation
- [Power Fx open-source interpreter (`Microsoft.PowerFx.Interpreter` on NuGet)](https://www.nuget.org/packages/Microsoft.PowerFx.Interpreter)

No devladlog.com blog guide: this series is built from vendor documentation only.
