# DEVLADLOG Deep Dive #5 — Employee onboarding portal (Power Apps + SharePoint + Entra inbound provisioning + Lifecycle Workflows)

Contoso's HR fills in **one form** for a new hire. The hiring manager approves it in Teams. A few minutes later the
account exists in Microsoft Entra, **disabled**, with department, job title, manager and hire date; the manager
receives a **Temporary Access Pass**; on day one the account is enabled, licensed and added to its groups, and a
seven-item checklist waits in SharePoint. Nobody types a password, and no code holds the right to create users.

```
Power Apps canvas app ─► SharePoint "Onboarding Requests" ─► flow: manager approval (standard connectors)
 (Taylor, HR)              Status: Submitted → Approved               │
                                                                      ▼
                  Azure Function (PowerShell 7.6, Flex Consumption, timer 5 min, user-assigned identity)
                  validate → manager's employeeId → unique UPN → SCIM bulk request
                                                                      │  POST .../synchronization/jobs/{id}/bulkUpload
                                                                      ▼
                  Microsoft Entra API-driven inbound provisioning: match externalId→employeeId, create/update user
                                                                      │
                  Lifecycle Workflows: pre-hire (TAP to manager, licence) · new hire (enable, welcome mail, groups)
                  Function, next pass: account found → "Account created" + checklist in "Onboarding Tasks"
```

- **Don't create users, send HR data.** The blog's Complete Guide creates users directly with Graph and needs
  `User.ReadWrite.All`, `Directory.ReadWrite.All` and more. Here the function sends SCIM records to the
  [API-driven inbound provisioning](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-concepts)
  endpoint, Microsoft's integration point for "any system of record", even a spreadsheet or a list. The provisioning
  service compares, creates or updates; Lifecycle Workflows own the joiner tasks.
- **Idempotent by design.** The list item ID becomes the employee ID (`NH00007`), sent as SCIM `externalId`; the
  provisioning app matches it to `employeeId` by default. Sending the same request twice updates one account.
- **Least privilege.** The function's identity has three Graph application roles —
  `SynchronizationData-User.Upload`, `User.Read.All`, `Lists.SelectedOperations.Selected` — plus `write` on **two
  lists**, not the site and not the directory. No secrets: Graph, storage and Application Insights all use the
  user-assigned identity.
- **Standard licences for people.** The app and the flow use only standard connectors (SharePoint, Office 365 Users,
  Approvals, Office 365 Outlook), so HR and managers need nothing beyond Microsoft 365. Lifecycle Workflows need
  Microsoft Entra ID Governance (lab: trial); API-driven provisioning works with Entra ID P1, P2 or Governance.

| Path | What it is |
|---|---|
| [`src/OnboardingSync/Modules/OnboardingSync/OnboardingSync.psm1`](src/OnboardingSync/Modules/OnboardingSync/OnboardingSync.psm1) | Everything: accent-free UPN aliases, unique UPN, hire date in UTC, validation, SCIM operation + bulk request (≤ 50), Graph client (token from the managed identity endpoint, retries on 429/5xx, `If-Match`), `Invoke-OnbSync` (Approved → Sent to Entra → Account created / Failed) |
| [`src/OnboardingSync/SyncOnboarding/run.ps1`](src/OnboardingSync/SyncOnboarding/run.ps1), [`function.json`](src/OnboardingSync/SyncOnboarding/function.json) | Timer trigger (`%Onboarding__Schedule%`), one log line per request |
| [`src/OnboardingSync/config/task-templates.json`](src/OnboardingSync/config/task-templates.json) | Day-one checklist, due dates in business days relative to the start date |
| [`src/OnboardingSync/host.json`](src/OnboardingSync/host.json) | Managed dependencies **off** (not supported on Flex Consumption) |
| [`contract/onboarding-lists.json`](contract/onboarding-lists.json) | The two lists, columns, statuses: one source of truth for app, flow, function and PnP script |
| [`provision/OnboardingLists.psm1`](provision/OnboardingLists.psm1), [`New-OnboardingLists.ps1`](provision/New-OnboardingLists.ps1) | PnP PowerShell: creates the lists (indexed Status and Request ID), idempotent, `-WhatIf` |
| [`provision/OnboardingAccess.psm1`](provision/OnboardingAccess.psm1), [`Grant-OnboardingAccess.ps1`](provision/Grant-OnboardingAccess.ps1) | Microsoft Graph PowerShell: assigns the three app roles to the managed identity and `write` on each list, prints the IDs for the app settings; idempotent, `-WhatIf` |
| [`flow/onboarding-approval.definition.json`](flow/onboarding-approval.definition.json) | Approval flow (reference definition, written by hand from the designer steps) |
| [`app/onboarding-portal.powerfx.json`](app/onboarding-portal.powerfx.json) | Power Fx for the two canvas app screens |
| [`infra/main.bicep`](infra/main.bicep) | Flex Consumption **FC1**, `powershell` **7.6**, storage without shared keys, App Insights with Entra auth, user-assigned identity, two Azure role assignments |
| [`tests/`](tests) | 82 Pester tests; [`FakeGraph.ps1`](tests/FakeGraph.ps1) is an in-memory Graph used only by tests |

## Test locally (no Azure, no tenant)

```bash
pwsh -NoProfile -c 'Invoke-Pester ./tests'            # Tests Passed: 82, Failed: 0 (about 12 s)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
```

How the tests work:
- **Unit** (33): name normalisation (`João Maria` `Conceição Gonçalves` → `joao.goncalves`, `Weiß` → `weiss`),
  Lisbon time zone in winter and summer, business days, validation, SCIM shape, the Graph client against a mocked
  `Invoke-WebRequest` (Retry-After, no retry on 412, UTF-8 body, refuses non-Graph hosts) and the managed identity
  token request and cache.
- **End to end** (15): the real `Invoke-OnbSync` and `run.ps1` against `FakeGraph`, which behaves the way Learn
  documents the services: list `$filter` + paging, `If-Match` → 412, `bulkUpload` requires `application/scim+json`
  and answers 202, and `RunProvisioning()` matches `externalId` to `employeeId`, resolves `manager.value` against
  `employeeId` and fails on a taken UPN. Scenarios: happy path including no duplicate tasks on later passes, paging,
  53 requests split into two bulk calls, UPN conflict, re-run, manager without employee ID, unknown manager, past
  start date, API 403 vs 503, an HR edit during the run, time-out.
- **Provisioning scripts** (18) with PnP and Graph PowerShell stubbed; **contract** (16): statuses and column names
  across contract, function, flow and Power Fx; Bicep compiled and checked (PowerShell 7.6, FC1, no shared keys,
  every app setting the function reads); `function.json`, `host.json`.

Tested with PowerShell 7.6, Pester 6.2.0, Bicep CLI 0.49.2. The function uses no PowerShell modules at all.

## Deploy (needs an Azure subscription and the lab tenant)

The full runbook (users, lists, provisioning app, grants, flow, app, Lifecycle workflows) is in [`demo.md`](demo.md).
Azure part:

```bash
az deployment group create -g rg-mglab-deep-dive-05 -f infra/main.bicep -p infra/main.bicepparam -p upnDomain=<domain>
pwsh ./provision/Grant-OnboardingAccess.ps1 -IdentityClientId <identityClientId> -HostName <tenant>.sharepoint.com
az deployment group create ... -p siteId=... requestsListId=... tasksListId=... provisioningServicePrincipalId=... provisioningJobId=...
cd src/OnboardingSync && func azure functionapp publish <functionAppName>
```

## What we learned / gotchas

- **The provisioning service matches managers by `employeeId`.** `manager.value` must be the manager's externalId,
  i.e. their employeeId in Entra. Lab users have none by default; a manager without one would leave the new hire
  without a manager, and the TAP e-mail without a recipient. The function fails such a request with that message.
- **UPN uniqueness is the client's job** (Learn FAQ), and a UPN can't contain accent characters (Learn, Create user).
  We normalise and try `alias`, `alias2` … `alias9`, re-using the name that already belongs to the same employee ID.
- **The hire date is a timestamp.** Lifecycle Workflows evaluate in UTC and the TAP task uses the hire date as the
  TAP start time (or now, if it's in the past). We send 09:00 Europe/Lisbon converted to UTC.
- **New workflows with "Equal to" have no catch-up window** (Learn, execution conditions): a user whose data arrives
  after that UTC day is never processed. Use *Within* / *Between*, and reject requests with a past start date.
- **Run on demand ignores execution conditions** and takes at most 10 users; scheduled runs default to every
  3 hours (1–24). The demo runs the workflows on demand.
- **TAP task preconditions:** the TAP policy must be enabled, and the user must not have other authentication
  methods, sign-ins or role assignments. Fine for a brand-new account, not for re-testing with an old one.
- **Notification e-mail is mandatory** on the provisioning app, or the job goes into quarantine; *Provision on
  demand* isn't supported for API-driven provisioning. `bulkUpload` answers 202 = *staged*; status comes later, so the
  list moves to *Sent to Entra* and the next pass looks for the account.
- **Flex Consumption doesn't support PowerShell managed dependencies.** No Graph SDK: the token comes from the managed
  identity endpoint (`IDENTITY_ENDPOINT`, `X-IDENTITY-HEADER`, `client_id` for a user-assigned identity).
- **PowerShell 7.4 reached end of support on 10 November 2026** in Azure Functions; 7.6 is GA on Flex Consumption.
- **Dates from Graph arrive as `DateTime` (UTC) after `ConvertFrom-Json`**, not strings: we convert explicitly. A
  test failed on exactly this before we did.
- **Filter on indexed columns**, one at a time (Learn, List items): Status and Request ID are indexed.
- **`If-Match` on list updates**: a 412 means HR edited the item while the pass ran; we leave it for the next pass
  (safe, because sending again updates the same account).
- **Not verified in the lab yet (needs tenant):** that `Lists.SelectedOperations.Selected` + a list `write` grant
  covers reading and patching items through Graph (fallback: `Sites.Selected` + site `write`); the default attribute
  mappings of the provisioning app (`userName` → `userPrincipalName`, `active` → `accountEnabled`); which eTag Graph
  expects in `If-Match` (we send the listItem `eTag`); the flow definition and Power Fx were written by hand and must
  be replaced by the exported/built versions; end-to-end timing.

## References

- [API-driven inbound provisioning concepts (permissions, limits, near real-time)](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-concepts) · [Configure the app (notification e-mail, no provision on demand)](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-configure-app) · [Grant access to a managed identity](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-grant-access)
- [bulkUpload API (SCIM, 50 operations, 202 + Location)](https://learn.microsoft.com/graph/api/synchronization-synchronizationjob-post-bulkupload) · [FAQ: matching externalId→employeeId, unique UPNs](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-faqs) · [Custom attributes (HireDate → employeeHireDate)](https://learn.microsoft.com/entra/identity/app-provisioning/inbound-provisioning-api-custom-attributes)
- [Create user (UPN characters, User.Create)](https://learn.microsoft.com/graph/api/user-post-users) · [user resource (employeeId max 16, $filter)](https://learn.microsoft.com/graph/api/resources/user)
- [Lifecycle workflow templates](https://learn.microsoft.com/entra/id-governance/lifecycle-workflow-templates) · [Built-in tasks (TAP task preconditions and start time)](https://learn.microsoft.com/entra/id-governance/lifecycle-workflow-tasks) · [Execution conditions and catch-up window](https://learn.microsoft.com/entra/id-governance/lifecycle-workflow-execution-conditions) · [Run on demand](https://learn.microsoft.com/entra/id-governance/on-demand-workflow) · [Customize the schedule](https://learn.microsoft.com/entra/id-governance/customize-workflow-schedule)
- [Selected permissions in SharePoint (Lists.SelectedOperations.Selected)](https://learn.microsoft.com/graph/permissions-selected-overview) · [Create permission on a list](https://learn.microsoft.com/graph/api/list-post-permissions) · [List items ($filter, indexed columns)](https://learn.microsoft.com/graph/api/listitem-list) · [Update listItem (if-match → 412)](https://learn.microsoft.com/graph/api/listitem-update)
- [Flex Consumption: supported versions, no managed dependencies](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan) · [PowerShell versions and end of support](https://learn.microsoft.com/azure/azure-functions/functions-versions) · [Managed identity REST endpoint](https://learn.microsoft.com/azure/app-service/overview-managed-identity#rest-endpoint-reference) · [Timer trigger (single instance, no retry)](https://learn.microsoft.com/azure/azure-functions/functions-bindings-timer)
- Blog: [Building an Employee Onboarding Portal — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-04-07-building-employee-onboarding-portal-azure-powerapps-sharepoint/)
