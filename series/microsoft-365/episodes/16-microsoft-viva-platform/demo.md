# Demo shot list — DEVLADLOG Microsoft 365 #16: Microsoft Viva Platform

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none (no Hyper-V VM, so no address from 10.50.0.0/24 is used; Azure and Power Platform are not needed) |
| Tenant | Lab tenant with Viva Engage (Microsoft Graph `/employeeExperience`), Teams, Entra admin center. The tenant's Engage network must be in **native mode**: the communities API does not work for legacy or external networks (Learn). Creates three Engage communities; all are deleted in tear-down |
| Lab users | **`labadmin`** (the recording account; runs apply and audit). **`alex.demo` (Alex Demo)** for the Teams screen (own browser profile). `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` are owners/members from the config |
| Licences / trials | Microsoft 365 E5 trial. Viva Engage and Viva Connections are available to Microsoft 365 / Office 365 enterprise plans (Learn: Viva service description), so nothing extra is bought. **Not used**: Viva Suite / Viva Learning (Learning provider API), Viva Insights premium, Microsoft 365 Copilot (the lab has no Copilot licence: no Copilot feature is shown or faked). Cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.2+ with `Microsoft.Graph.Authentication`, two browser profiles (labadmin, alex.demo), `pipeline/mask.js` |

Everything in `src/` and `tests/` already ran in the build container (54 Pester tests with the real Graph PowerShell
module present, offline plan and offline audit from a fictional inventory). This file lists what the human-supervised
session sets up and records in the **lab tenant**. Every Graph call below is **needs tenant**, and every screen shows the
real product. `tests/fixtures/*` and `sample/*` are for the automated tests only and never appear on screen.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Viva Engage network in native mode | Viva Engage admin center → check the network is native (Learn: the communities API works only for native mode). If it is not, the episode cannot be recorded in this tenant: stop and tell the lead | none |
| PowerShell 7.2+ + `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Consent | Delegated scopes asked by the runner: `Community.ReadWrite.All`, `Group.ReadWrite.All`, `User.ReadBasic.All` (apply); `Community.Read.All`, `EngagementRole.Read.All`, `Group.Read.All`, `User.ReadBasic.All` (audit). An administrator consent prompt is likely: approve once as `labadmin` | none |
| Who may create communities | Not verified: the network may restrict who can create communities. If the create call answers 403 for `labadmin`, check the Engage admin center settings before anything else | none |
| Browser | `pipeline/mask.js` loaded for Viva Engage and Teams | none |

## Setup (before recording)

1. Entra admin center: note the real UPNs of `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`, `labadmin`.
2. Copy `src/communities.json` to an uncommitted `src/communities.lab.json` and change only the `@contoso.com`
   addresses to the real UPNs (also in `settings.allowedNetworkAdmins`). Pass `-ConfigFile ./communities.lab.json` to every command.
   Note that the runner's account (`labadmin`) becomes **owner of every community it creates** (Learn: delegated create);
   the config does not list it, and the script does not remove it.
3. Run the tests on the recording machine: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` →
   `Tests Passed: 54` (52 + 2 skipped if `Microsoft.Graph.Authentication` is not installed).
4. List the Engage roles once and write the exact role names in README: `Invoke-MgGraphRequest GET /v1.0/employeeExperience/roles`.
   The audit matches names containing `Network Admin`; if the tenant spells it differently, fix the match in `Get-VivaFinding` first.
5. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/apply.jpg` — "WhatIf, then create the communities" (**needs tenant**, creates 3 communities)
Signed in as `labadmin` (interactive sign-in inside the runner).
```powershell
cd src
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Apply -WhatIf
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Apply -Verbose   # creating takes 31+ s per community (polling)
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Apply            # second run: InSync rows
```
Expected: `CreateCommunity … Created (…)` x3, `AddOwner` and `AddMember` rows (`Already there` for the creator), then only `InSync`.
Then **Viva Engage on the web**: the communities in the sidebar, one opened with owners and members. Mask the tenant name.
**Check and note in README**: how long a create really takes; whether the header is `Operation-Location` or `Location`
(`-Verbose` does not print it: look in the Graph response if in doubt); whether adding an owner to the group
(`owners/$ref`) also makes them an Engage community admin right away, and whether an owner who is not a member is accepted.

### 2. `screens/audit.jpg` — "The audit, live" (**needs tenant**, read-only)
First make the tenant look like a real quarter, in the Engage UI (about three minutes, show none of it):
- **Project Falcon - Launch**: remove `sam.demo` as owner, leaving fewer owners than `minOwners` (`FewOwners`). To get `NoOwner`, a community must lose all owners: do this to **Falcon Customer Stories** only if Engage allows it, otherwise skip that finding.
- **Contoso Ask Anything**: change privacy from public to private in the community settings (`PrivacyDrift`).
- Add `jordan.demo` as **Network Administrator** (Engage admin center, admins). With `labadmin` and `alex.demo` already there this makes a third or fourth admin: `UnexpectedNetworkAdmin` for `jordan.demo`; set `maxNetworkAdmins` to 2 in the lab config to also get `TooManyNetworkAdmins`.
```powershell
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Audit -OutFile ./viva-audit.md -SaveInventory ./inventory.lab.json
```
Expected rows: `FewOwners` (and `NoOwner` if achieved), `PrivacyDrift`, `UnexpectedNetworkAdmin`, maybe `TooManyNetworkAdmins`. Show `viva-audit.md` in the editor.
Rewrite the narration's specifics to match the screen. The tenant may also contain communities that were already there: they show as `NotInConfig` (Info).

### 3. `screens/teams.jpg` — "What people see" (**needs tenant**)
Sign in to Teams as `alex.demo`. Open the **Viva Engage** app: the community list shows the script's communities.
Then the **Viva Connections** app only if the tenant already has a home site set up: show it as it is. Do not set it up
for the recording (it is a SharePoint/SPFx topic, not this script). Do not open any Copilot feature (no licence).
If Connections is not available, record Engage only and change the narration's second half.

## Masking checklist
- Tenant name/domain, UPNs of the lab users, group Object IDs, community IDs, `inventory.lab.json` (contains group IDs).
- The browser address bar in Viva Engage and Teams (contains the network and community IDs).

## Tear-down
1. **Delete the three communities** in Viva Engage (as `labadmin` or each owner): this deletes their Microsoft 365 groups, notebooks and plans (Learn), which is intended here because the script created them.
   Do **not** delete communities that existed before the recording (they show as `NotInConfig`).
2. Undo the manual changes: remove `jordan.demo` as Network Administrator; restore any privacy or owner you changed on communities that stay.
3. Delete `communities.lab.json`, `inventory.lab.json`, `viva-audit.md`; `Disconnect-MgGraph`; clear the browser profiles' sign-ins.
