# Demo shot list — DEVLADLOG Deep Dive #5, Employee onboarding portal

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 82 Pester tests pass, `bicep build` / `bicep lint` clean.

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge for Power Apps, SharePoint, the Entra admin center and Outlook on
the web, Teams (web or desktop) for the approval, a terminal for `az` / `func` / `pwsh`. **No Hyper-V VM is needed.**

**Azure** — resource group `rg-mglab-deep-dive-05`, West Europe (check Flex availability first:
`az functionapp list-flexconsumption-locations -o table`)

| Resource | SKU | Estimated cost for a recording day |
|---|---|---|
| Function app `func-onb-<token>` on a Flex Consumption plan | **FC1**, PowerShell **7.6**, 2,048 MB instances, no always-ready instances | billed per execution and GB-second; a 5-minute timer for one day is ~290 short runs: cents |
| Storage account `stonb<token>` | Standard_LRS, shared keys off (code package + timer locks) | cents |
| User-assigned managed identity `id-onb-<token>` | — | free |
| Log Analytics + Application Insights | PerGB2018, 30-day retention | a few MB: cents |

Total: **well under €1** (check the [pricing calculator](https://azure.microsoft.com/pricing/calculator/) on the day).
Delete the resource group right after recording. Budget `mglab-monthly` (€30) is not at risk.

**Microsoft 365 lab tenant**
- **Licences:** Microsoft 365 E5 trial (Entra ID P1/P2 for API-driven provisioning, group features, Exchange),
  **Entra ID Governance trial** for Lifecycle Workflows. The new hire consumes **one** E5 trial licence (assigned by
  the workflow) until tear-down. **No premium Power Platform licence is needed**: the canvas app and the flow use only
  standard connectors (SharePoint, Office 365 Users, Approvals, Office 365 Outlook). If the lab later swaps the flow
  for a premium action, the flow owner starts the self-service Power Automate Premium trial.
- **Users (fictional):** **Taylor Demo** = HR (submits the request), **Sam Demo** = hiring manager (approves, receives
  the TAP), **Lab Admin** (`labadmin`) = admin steps and recording account. **Casey Demo** is *created by the demo*
  (by the provisioning service) and deleted in tear-down.
- **SharePoint:** new team site `/sites/hr-lab` (created in setup, deleted in tear-down).
- **Power Platform:** environment **`DEV`**, solution `Employee onboarding` (canvas app + flow).
- **Entra:** one enterprise app *API-driven provisioning to Microsoft Entra ID*; two Lifecycle workflows; the
  Temporary Access Pass policy enabled for the lab; security group `Sales lab team`.

**Local tools on the laptop:** Azure CLI, Azure Functions Core Tools v4, Bicep CLI, PowerShell 7.4+ with
`PnP.PowerShell` (the lab's PnP app registration from episode 1) and `Microsoft.Graph.Authentication`.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/05-employee-onboarding-portal
   pwsh -NoProfile -c 'Invoke-Pester ./tests'        # expect Tests Passed: 82
   ```
2. **Lab users** (Entra admin center as Lab Admin → Users → *Edit properties*): Sam Demo → Job information →
   **Employee ID `E1002`**, Department `Sales`. Check Sam and Taylor have a mailbox (E5). Write down any previous
   values so tear-down can restore them. Create security group **`Sales lab team`** (assigned membership, no members).
3. **SharePoint site and lists**: create the team site *HR lab* (`/sites/hr-lab`), then
   ```powershell
   ./provision/New-OnboardingLists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/hr-lab -ClientId <PnP app id> -WhatIf
   ./provision/New-OnboardingLists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/hr-lab -ClientId <PnP app id>
   ```
   Run it twice: the second run shows `Exists` everywhere. Edit the *All Items* view of *Onboarding Requests*: Title,
   Department, Start date, Status, Employee ID, Sign-in name, Provisioning note.
4. **Provisioning app** (Entra admin center → Enterprise apps → New application → search **API-driven** → *API-driven
   provisioning to Microsoft Entra ID*), name `Contoso HR onboarding (API)` → Create.
   - Provisioning → Get started → mode **Automatic** → Save. In **Settings**, set the notification e-mail to Lab
     Admin and Save again (Learn: without it the job goes into quarantine).
   - **Edit Provisioning** → expand **Mappings** → the attribute mapping link → **Advanced Options** → *Edit target
     User attributes* (Learn's custom-attributes tutorial): at the end of the list add
     `urn:ietf:params:scim:schemas:extension:contoso:1.0:User:HireDate` and
     `urn:ietf:params:scim:schemas:extension:contoso:1.0:User:UsageLocation`. Save.
   - **Add New Mapping**: HireDate → `employeeHireDate` and UsageLocation → `usageLocation` (Direct). **Check**
     that `externalId` → `employeeId` is the matching attribute (default), that `userName` flows to
     `userPrincipalName` (if the default is an expression, change it to Direct `[userName]`), that `active` flows to
     `accountEnabled`, and that `manager` is mapped. Record what the defaults were in README "What we learned".
   - Overview → **Start provisioning**. *View technical information* → copy the **Provisioning API Endpoint**: it
     contains the service principal ID and the job ID (`.../servicePrincipals/<spId>/synchronization/jobs/<jobId>/bulkUpload`).
     Never show it on camera.
5. **Azure, first deployment** (gives us the identity)
   ```bash
   az login                                            # Lab Admin, off camera
   az group create -n rg-mglab-deep-dive-05 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-05 -f infra/main.bicep -p infra/main.bicepparam \
      -p upnDomain=<lab verified domain> --query properties.outputs -o json > /tmp/onb-outputs.json
   ```
6. **Grant the identity** (Graph app roles + list grants) and get the list IDs
   ```powershell
   $id = (Get-Content /tmp/onb-outputs.json | ConvertFrom-Json).identityClientId.value
   ./provision/Grant-OnboardingAccess.ps1 -IdentityClientId $id -HostName contoso.sharepoint.com -WhatIf
   ./provision/Grant-OnboardingAccess.ps1 -IdentityClientId $id -HostName contoso.sharepoint.com
   ```
   Run twice (second run: `Exists`). Check in Enterprise apps (remove the *Application type* filter) → the identity →
   Permissions: exactly the three Graph roles.
7. **Azure, second deployment** with the IDs, then publish the code
   ```bash
   az deployment group create -g rg-mglab-deep-dive-05 -f infra/main.bicep -p infra/main.bicepparam \
      -p upnDomain=<domain> siteId=<SiteId> requestsListId=<id> tasksListId=<id> \
         provisioningServicePrincipalId=<spId> provisioningJobId=<jobId> -o none
   cd src/OnboardingSync && func azure functionapp publish $(jq -r .functionAppName.value /tmp/onb-outputs.json) && cd ../..
   ```
   In the function's *Log stream*, the first pass should log `Sync finished: 0 item(s) changed.` If it logs 403 on
   the list, the list-level grant isn't enough for item updates in this tenant: grant `Sites.Selected` + site `write`
   instead (note it in README).
8. **Flow** `Onboarding request approval` in solution `Employee onboarding` (`DEV`), environment variables
   `mgl_HrSiteUrl`, `mgl_OnboardingRequestsList`: trigger **SharePoint › When an item is created**, trigger condition
   from `flow/onboarding-approval.definition.json` → **Approvals › Start and wait for an approval** (Approve/Reject -
   First to respond, assigned to *Hiring manager*, title/details/link as in the JSON) → **Condition** outcome =
   Approve → **Update item** Status = Approved, Provisioning note = responder + comments; else Status = Rejected and
   **Send an email (V2)** to the item's author. Export the solution afterwards, copy the workflow definition over the
   JSON file and re-run `Invoke-Pester ./tests/Contract.Tests.ps1`.
9. **Canvas app** `Onboarding Portal` (tablet) in the same solution: data sources *Onboarding Requests* and *Office 365
   Users*; two screens and every formula from `app/onboarding-portal.powerfx.json`. Share with Taylor (user).
10. **Temporary Access Pass**: Entra admin center → Authentication methods → Temporary Access Pass → Enable for
    *All users* (lab only; note the previous state), minimum lifetime ≤ 1 hour, maximum ≥ 8 hours, one-time use allowed.
11. **Lifecycle workflows** (ID Governance → Lifecycle workflows → Create workflow), both created with **Enable
    schedule unchecked** (we run them on demand):
    - `Contoso pre-hire` from template **Onboard pre-hire employee**: trigger employeeHireDate, 7 days before; scope
      rule `(department eq 'Sales')`. Tasks: **Generate TAP and send email** (activation 480 minutes, one-time use)
      and add **Assign licenses to user** (Microsoft 365 E5 trial) so the mailbox exists before day one.
    - `Contoso new hire` from template **Onboard new hire employee**: tasks **Enable user account**, **Send welcome
      email**, **Add user to groups** (`Sales lab team`).
12. **Dry run** once end to end with a throwaway name (e.g. *Jordan Test*), then delete that user (and from *Deleted
    users*) and its list items so the take starts clean. Start date = **today** and record **after 09:00 Lisbon
    time**: the TAP starts at the hire date (09:00 today), so it is valid immediately.

## Screens to capture (1920×1080, browser zoom 100 %, light theme)

| Scene id | File | What must be on screen |
|---|---|---|
| `app-screen` | `screens/app-new-request.jpg` | Canvas app as **Taylor**: New request filled in (Casey / Demo / Sales / Sales representative / Sam Demo from the people picker / today), then *My requests* with Casey Demo **Submitted**. B-roll (no scene): Sam approving in Teams → Approvals. |
| `provisioning-screen` | `screens/provisioning-logs.jpg` | Enterprise apps → *Contoso HR onboarding (API)* → Provisioning logs: one **Create** for source ID **NH0000x**, status **Success**; details pane with modified properties (userPrincipalName, accountEnabled **False**, employeeId, department, employeeHireDate, manager). |
| `list-screen` | `screens/list-account-created.jpg` | *Onboarding Requests*: Casey Demo, Status **Account created**, Employee ID, Sign-in name, note "… 7 onboarding tasks added". Second capture: *Onboarding Tasks* filtered to that request ID: seven rows with owners and due dates. |
| `tap-screen` | `screens/lcw-tap-email.jpg` | Lifecycle workflows → `Contoso pre-hire` → **Run on demand** for Casey → Workflow history: task *Generate TAP and send email* **Completed**. Then Sam's Outlook: the TAP e-mail for Casey Demo, **pass value fully masked**. |

After the take (not narrated, for README): run `Contoso new hire` on demand, confirm the account is enabled, Casey
gets the welcome e-mail and is in `Sales lab team`, and Casey can sign in at My Sign-ins with the TAP and register a
passkey. Record what happened in README.

## Masking

Run `pipeline/mask.js` before capturing. Mask the tenant name and the domain part of every address (keep `casey.demo`,
`sam.demo`, `taylor.demo` readable), the **Temporary Access Pass value (always, completely)**, the provisioning API
endpoint, service principal / job / object IDs, the function app and storage names, the subscription name. Never show
`/tmp/onb-outputs.json` or the identity's client ID.

## Tear-down

```bash
az group delete -n rg-mglab-deep-dive-05 --yes --no-wait      # function, storage, identity (its Graph roles and list grants go with it)
```
- Entra: delete **Casey Demo** (and permanently from *Deleted users*, which frees the E5 trial licence), delete both
  Lifecycle workflows, delete the *Contoso HR onboarding (API)* enterprise app, delete group `Sales lab team`,
  restore the Temporary Access Pass policy to its previous state, clear Sam's Employee ID and Department (or restore).
- Power Platform: delete the `Employee onboarding` solution (app + flow) in `DEV`.
- SharePoint: delete the *HR lab* site, then from the deleted sites list in the SharePoint admin center.
- The lab users stay (shared).
