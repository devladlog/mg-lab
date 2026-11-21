# Demo shot list — SharePoint #9 Teams and SharePoint

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **Teams + SharePoint** in the lab tenant (Microsoft 365 E5 trial, until 20 Dec 2026). Existing from earlier episodes: `/sites/Purchasing` (episode 3: page `how-to-buy`; episode 4: library `SupplierDocuments`), hub `/sites/Operations` (episode 7). Created here: the team *Contoso Purchasing Team* with its Microsoft 365 group and team site, a private channel site, a shared channel site, two tabs, the team site's hub association |
| Lab users | `labadmin` records (SharePoint Administrator, exists; team owner and owner of *Facilities Handover*); `jordan.demo` (team owner, owner of *Contract Negotiation*); `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo` (team members). Browser profiles: `alex.demo` and `riley.demo` for the Teams screens, each in its own profile |
| Entra app | The existing "MG Lab PnP" app (delegated). It needs these **delegated Microsoft Graph** permissions with admin consent: `Group.ReadWrite.All`, `ChannelMember.ReadWrite.All` (and `Group.Read.All`, `ChannelMember.Read.All` for the read-back; the write ones cover them in practice, add the read ones if `-Check` is refused). Remove what was added only for this episode in tear-down |
| Licences / trials | lab E5 licences; cost €0. No SharePoint Premium, no Advanced Management |
| Teams policy | Check that private and shared channel creation is allowed (Teams admin center → Teams → Teams policies; Learn: private channel creation is policy controlled). The plan creates them with `labadmin` as the caller; if a policy blocks it, say so in README and use a policy that allows it for the recording |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser (with `pipeline/mask.js`) for Teams on the web (teams.microsoft.com is fine for recording; the desktop app also works) |

The code scenes are real output from this folder (lint, Pester). The four `screen` scenes need the lab tenant.
**Needs tenant:** `Invoke-MgTeam`, `Get-MgTeamState`, `Wait-MgFilesFolder` and the `-Provision` / `-Check` paths of
`Invoke-TeamsIntegration.ps1`. Locally they are covered only by Pester tests that mock the real PnP cmdlets (parameter
names and types are checked, so are the shapes of the objects they read).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Episodes 3, 4 and 7 in place | `/sites/Purchasing` with `SitePages/how-to-buy.aspx` and the library `SupplierDocuments`; hub `/sites/Operations`. If one is missing, change the tab URLs and the hub URL in `purchasing.team.json` | €0 |
| SharePoint Administrator for `labadmin` | the hub association (`Get-PnPTenantSite`, `Add-PnPHubSiteAssociation`) | €0 |
| The six lab users have Teams licences | they have E5 (includes Teams). Sign each in to Teams once before recording so their first-run screens are out of the way | €0 |
| PowerShell 7.4+, PnP.PowerShell 3.x, Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |
| No team called *Contoso Purchasing Team* exists | The plan finds the team by display name (`Get-PnPTeamsTeam -Filter`). Look in the Teams admin center first | — |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/09-integration-with-teams
Invoke-Pester ./tests -Output Detailed                                     # expect 28 passed
$tenant = 'https://<lab-tenant>.sharepoint.com'                             # never on screen unmasked
$t = @{ TenantUrl = $tenant; AdminUrl = 'https://<lab-tenant>-admin.sharepoint.com'; ClientId = '<MG Lab PnP client id>'
        UpnSuffix = '<lab-tenant>.onmicrosoft.com' }                        # or the lab's custom domain

./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Provision -WhatIf
```
- The `-WhatIf` run must show `CreateTeam`, three `AddChannel`, two `AddTab` and `Associate`. Because the team and the
  channels don't exist yet, `-WhatIf` prints these from the plan without calling the tenant for them, and shows no
  `AddMember` (members are added to channels that exist: the real run adds Alex to the private channel and Sam to the
  shared one; `labadmin` and `jordan.demo` are the owners, already in).
- One device-code sign-in happens (the admin center): do it off camera. Dark terminal, font 18+, clear before each capture.
- Do the real `-Provision` **the day before** the browser screens, then look at the three sites once: the team site and
  the channel sites can take minutes (Graph: if a channel site doesn't provision after five minutes, the filesFolder call
  triggers it; `Wait-MgFilesFolder` does that for the hub step).
- **Check the user names.** If `alex.demo@<domain>` is not how the lab users sign in, adjust `-UpnSuffix`.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/provision.jpg` — scene `provision`**
   ```powershell
   ./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Provision
   ```
   Capture: `0 error(s), 0 warning(s)`, the "Where the files will live" table with `-> 3 SharePoint site(s)`, then
   `CreateTeam`, three `AddChannel`, `AddMember` ×2, `AddTab` ×2, `Associate`. **Record what really happens.** Check in
   particular:
   - Whether the first `Add-PnPTeamsChannel` works right after `New-PnPTeamsTeam` or needs a wait (the module reads the
     channels first and doesn't wait; if it fails, note the delay and add a pause in `Invoke-MgTeam`).
   - Whether `Add-PnPTeamsChannel -ChannelType Shared -OwnerUPN` is accepted for `labadmin` (shared channels are created
     with one owner).
   - Whether `Add-PnPTeamsTab -Type SharePointPageAndList -WebsiteUrl` accepts the library URL
     (`…/SupplierDocuments/Forms/AllItems.aspx`). If not, use the library's home page or a page, change the plan and README.
   - Whether the `Associate` step finds the team site (`Wait-MgFilesFolder` on General).

2. **`screens/files.jpg` — scene `files`**
   Browser as **Alex Demo**: Teams → Contoso Purchasing Team → *Supplier Reviews* → **Files** → **Open in SharePoint**.
   Capture the team site's *Documents* library with the folders *General* and *Supplier Reviews*, and the hub bar
   *Contoso Operations* if it shows (the hub theme can take a while on associated sites). Then *Contract Negotiation* →
   **Files** → **Open in SharePoint**: a different site. Capture both address bars (tenant host masked, the site names
   left visible). **Record what really happens:**
   - What the private channel site is called and whether its Documents library already has a folder (Learn: new private
     channels aren't created with a folder by default). Note it in README.
   - Whether *Facilities Handover* shows the same pattern.
   - Whether the hub bar shows on the channel sites (Learn: associating the parent associates the channel sites).
   Then in a second profile as **Riley Demo** (team member, not in the private channel): *Contract Negotiation* isn't in
   the channel list. Capture it.

3. **`screens/tab.jpg` — scene `tab`**
   Browser as **Alex Demo**: *General* channel with the tab row *Posts · Files · How to buy*, the buying guide open.
   Then *Supplier Reviews* with *Supplier Documents*. If a tab shows a sign-in or "refused to connect" message instead of
   the page, record it, and put it in README ("Not verified yet").

4. **`screens/check.jpg` — scene `check`**
   ```powershell
   ./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Check     # expect "No findings."
   ```
   Then in Teams as **Jordan Demo** (owner of *Contract Negotiation*): channel → ⋯ → **Manage channel** → Members →
   remove **Alex Demo**. Run `-Check` again: expect `TL004  channel 'Contract Negotiation'  alex.demo is not a member of
   the channel.` and `1 error(s), 0 warning(s)`. Capture both runs. Run `-Provision` once more afterwards to restore
   (expect one `AddMember` line). If `-Check` reports differences right after provisioning, record them: they are the gaps
   in "Not verified yet" (for example `Email` empty in the member list, or a tab URL that Teams rewrote); fix
   `Get-MgTeamState` / `Test-MgTeamLive` and the README.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in address bars, in `$t` and in the `-UpnSuffix`; PnP client id; device-login codes; the Teams group object
  ID if it shows.
- Account pictures/initials of real people (only lab users should appear); the admin account name.
- Site, team and user names are fictional.

## Tear-down
Keep the team if no other episode needs it; it isn't used by episode 10. Otherwise:
```powershell
Connect-PnPOnline -Url $t.AdminUrl -ClientId $t.ClientId -DeviceLogin
$g = (Get-PnPTeamsTeam -Filter "displayName eq 'Contoso Purchasing Team'").GroupId
Get-PnPTenantSite -Filter "Url -like '*contoso-purchasing-team*'"      # note the team site and the two channel sites
Remove-PnPTeamsTeam -Identity $g -Force                                  # deletes the group; the sites follow it
# optional: purge now instead of waiting for the 30-day soft delete
Remove-PnPDeletedMicrosoft365Group -Identity $g
Get-PnPTenantDeletedSite                                                 # check what is left; Remove-PnPTenantDeletedSite -Identity <url> -Force
```
Check in the Teams admin center and the SharePoint admin center that the team and its three sites are gone (deleted
sites stay in the recycle bin for a while). Remove `Group.ReadWrite.All` / `ChannelMember.*` from the PnP app if they
were added only for this episode, and delete any browser-profile sessions of `riley.demo`.
