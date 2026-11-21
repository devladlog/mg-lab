# Demo shot list - Copilot & AI #9 Copilot in SharePoint and SharePoint Agents

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant: Microsoft 365 E5 trial (SharePoint Online, Microsoft 365 admin center). The **Contoso Vendor Management Office** communication site (`contoso-vmo`, libraries Policies and Restricted) from episode 3: re-create it with that episode's `New-VendorKnowledgeSite.ps1` if it was torn down, and upload the five policy documents |
| Accounts | `labadmin` (Global Administrator, SharePoint administrator, site owner, recording account). `sam.demo` is optional (a Visitors-group member without access to Restricted) for the "answers are trimmed per user" take |
| **Licence: Microsoft 365 Copilot** | **The lab does NOT have it, and three screens need it** (`ask`, `siteai`, `skills-page`). Learn (*Get started with Copilot in SharePoint*): "Users must have an active Microsoft 365 Copilot license". **Owner decision: buy and assign one seat to `labadmin` for the recording window**, then remove it. Price: the lab users hold Microsoft 365 E5, so the enterprise add-on applies; **its price was not verifiable here** (Microsoft's own pricing page links to a separate enterprise page; a Microsoft Q&A answer says about US$30 per user per month, which is not an official source). The owner reads the price at purchase. For reference only: the *Microsoft 365 Copilot Business* add-on, which is for Business-plan tenants of up to 300 users (Learn, *License options for Microsoft Copilot*), was listed at US$18 per user per month with annual billing and US$25.20 with monthly billing on Microsoft's pricing page on 21 November 2026 |
| Other cost | Copilot Credits (advanced work) are **not** needed: do not create a spending policy and do not accept any prompt that asks to spend credits (Learn: users with credits are asked to confirm; read the prompt and decline). Pay-as-you-go for SharePoint agents is **not** set up: only look at its page. Azure: none |
| Entra | One app registration for PnP PowerShell, as in episode 3 (`Register-PnPEntraIDApp -ApplicationName "MGLab PnP" -Tenant <tenant>.onmicrosoft.com -Interactive`), app id kept out of the repo and off camera. Delete it in tear-down |
| Recording machine | Windows lab laptop: browser profile for `labadmin`; PowerShell 7 with `PnP.PowerShell` 3.x; Python 3.10+ with `pip install -r src/requirements.txt`; terminal dark theme, 18 pt, window 1600x900 |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| `agentfiles` inventory, triage sheet, plan, skill lint | yes: 24 pytest tests (inventory, plan, skill lint) plus real CLI runs on the fictional sample files | - |
| `Get-AgentFileInventory.ps1` | yes: parsed and run under `pwsh` with stand-ins for `Connect-PnPOnline` and `Submit-PnPSearchQuery` (5 tests, test only): query text, selected columns, CSV that the Python side reads, empty result, URL validation | **first real run**: cmdlet and parameter names were checked against the PnP docs, the managed properties against the SharePoint Server property reference, not against a live tenant |
| `SKILL.md` upload and run | the file passes `skill-lint` (rules borrowed from Copilot Studio, Agent Builder, Visual Studio: Learn has no SharePoint schema) | **yes**: whether *Site skills > Upload* accepts it, and what Copilot does with it |
| Everything Copilot or the admin center shows | no | **record it** |

Open points to confirm on the tenant (each can change a scene):
1. Whether the tenant already moved to the Agent Builder creation flow (Learn: rolling out from mid-November 2026). If
   *Create an agent* in SharePoint still saves a `.agent` file, create the three sample agents in Setup step 4; if not, there
   are no `.agent` files to find and the `inventory` scene shows the honest empty result (see below).
2. Whether the Site AI panel and the Copilot button appear for `labadmin` once the licence is assigned (it can take time).
3. Whether Copilot in SharePoint is available on the site (Learn: Restricted Content Discovery hides it; this tenant has no
   SharePoint Advanced Management, so RCD should not be set).
4. What `Upload` on the Site skills page says about our `SKILL.md`.
5. Which columns of the search come back populated (`ViewsLifeTime`, `ViewsRecent` can be empty for new files).

## Prerequisites
- `cd series/copilot-ai/episodes/09-copilot-in-sharepoint-and-sharepoint-agents`
- `python -m pip install -r src/requirements.txt` and `python -m pytest -q` -> `29 passed`.

## Setup (the day before)
1. Recreate the VMO site if needed (episode 3 `New-VendorKnowledgeSite.ps1`, run as `labadmin`). Check Policies opens for `labadmin`.
2. Purchase and assign **one Microsoft 365 Copilot seat to `labadmin`** (owner). Microsoft 365 admin center > Users > Active users >
   labadmin > Licenses and apps. Wait until the Copilot button shows on the site (can take hours).
3. In the Microsoft 365 admin center, Copilot > Cost management: **do not** add a spending policy.
4. Only if the tenant still creates `.agent` files: as `labadmin` on `contoso-vmo` create three agents in the old builder with
   different purposes (a Q and A agent on the Policies library named *Vendor Desk*, a second one named *Renewals Helper*
   limited to the renewals document, and one more on any other site). Give each a few views. These are the agents the
   inventory will find; the sample CSV in `src/samples` is **not** used in a tenant screen.
5. Two sample vendor requests in Policies for the skill (fictional): one complete (name, category security, 12,000 euros per
   year, justification), one with no justification and 30,000 euros per year. Put them in `Policies` as `.docx`.
6. Run the collector once off camera to know the real output: `./src/scripts/Get-AgentFileInventory.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> -OutFile out/agent-files.csv`.
   Search needs time to index new files.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `ask` | `screens/copilot-sharepoint.jpg` | **Needs the Copilot licence.** `contoso-vmo` Policies library as `labadmin`, Copilot chat open. Prompt: *Which vendor requests above 25,000 euros need a security review, and who approves them?* Expected from the onboarding policy: the finance director approves, after a security review. Record what really appears, including citations. Optional second take as `sam.demo` (no Copilot licence): record what he sees (no Copilot button expected: Learn says users need the licence) |
| `siteai` | `screens/site-ai.jpg` | **Needs the Copilot licence.** Gear > **Site AI**. Show the three options from Learn: which agent opens from the header (Copilot in SharePoint or a custom agent), hide the Copilot button for visitors, advanced document processing. Change nothing. Do not turn on *advanced document processing* (it can use credits) |
| `inventory` | `screens/inventory.jpg` | Terminal: the collector against the tenant, then `python -m agentfiles inventory out/agent-files.csv`. **Real result only.** If there are no `.agent` files, the script prints *No .agent files visible to you* and the summary shows 0: record that and say on camera that the tenant already creates agents with Agent Builder, which is the situation the plan is for. Optional: the browser search for `*.agent` on the site next to it (Learn describes that search) |
| `skills-page` | `screens/site-skills.jpg` | **Needs the Copilot licence.** Gear > **Site skills** > Create or upload > Upload > `src/skills/vendor-intake-check/SKILL.md`. Show the skill enabled in the list (name, source, status). Then in Policies select the two vendor requests and prompt *Run vendor-intake-check on the selected documents*. Show the answer and the *Vendor intake issues* list. If Copilot asks to spend Copilot Credits, **decline** and record the prompt. If Upload rejects the file, record the message: it replaces the `gotchas` scene's last bullet |
| `admin` | `screens/admin-agents.jpg` | Microsoft 365 admin center > **Copilot** > **Billing & usage** > Pay-as-you-go services > *Connect a service*: *SharePoint agents* in the list (do not connect). Then the **Agents** page (Copilot Control System) as the inventory of agents used in Copilot Chat. Read only. Record empty states as they are |

The `plan` scene in the script is the Python tool on the repo's **fictional sample files**, shown as code with the label "sample
data" in the narration. It is not a product screen; do not present it as the tenant's data. If the real inventory has at least
three agents, you may instead record the real `triage-template` and `plan` run and swap the scene's code block.

Masking: tenant name and every SharePoint URL, the app registration id, the Entra app name if it shows the tenant, email domains
in the account menu, and any licence purchase screen (price is read off camera). Never show a password prompt.

## Tear-down
1. Remove the Copilot seat from `labadmin` (Licenses and apps) and cancel/let the purchase lapse per the owner's choice.
2. Disable or delete the `vendor-intake-check` site skill (Site skills page), delete the *Vendor intake issues* list and the two
   sample vendor requests, and delete any `.agent` files created in Setup step 4 (they go to the recycle bin: empty it).
3. If the VMO site was created only for this episode: `New-VendorKnowledgeSite.ps1 -Remove` (episode 3).
4. Delete the Entra app registration "MGLab PnP". Remove `out/` and browser sign-ins you do not need.
