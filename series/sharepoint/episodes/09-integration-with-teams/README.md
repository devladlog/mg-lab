# DEVLADLOG SharePoint #9 — Teams and SharePoint, as code

Contoso Purchasing has a communication site ([episode 3](../03-modern-sites-pages/)), a supplier library
([episode 4](../04-document-management/)) and a hub, **Contoso Operations** ([episode 7](../07-hub-sites-navigation/)).
The purchasing people also want to talk where they work. This episode builds **Contoso Purchasing Team** and, more
importantly, shows where its files really go: a Teams channel is a SharePoint folder only for *standard* channels. Each
*private* and each *shared* channel gets a SharePoint site of its own. Everything is in a **team plan** (JSON) and a
PowerShell module that:

- **lints the plan** before anything exists: team (display name, owners, visibility), channel names against Learn's list
  (characters, reserved words, edges, 50 characters), unique names, channel types, owners for private and shared
  channels, private channel members that must be in the team, the 1,000-channel limit, tab types that private and shared
  channels do not support, tab URLs, the hub URL
- **shows where the files will live**: the team site (one folder per standard channel) and one site per private or
  shared channel, so you know how many sites the team creates
- **provisions** with PnP PowerShell, idempotently: the team (owners and members), the channels (private and shared ones
  with their owner), the channel members, SharePoint page or list tabs, and the team site's hub association
- **reads it all back** and reports the drift, asking Graph where each channel's files folder is: missing channels,
  a channel of another type, people missing from private and shared channels, missing or redirected tabs, files folders
  on the wrong kind of site, the hub

Episode 10 stays on SharePoint and document processing; it doesn't need this team.

| Path | What it is |
|---|---|
| [`src/MgTeams.psm1`](src/MgTeams.psm1) | The module: `Test-MgChannelName`, `Test-MgTeamPlan` (TP001–TP013), `Get-MgChannelStorage`, `Test-MgTeamLive` (TL001–TL007), `ConvertTo-MgUpn`, `Get-MgSiteKey`, `Invoke-MgTeam`, `Get-MgTeamState` |
| [`src/teams/purchasing.team.json`](src/teams/purchasing.team.json) | The plan: one private team (two owners, four members), a standard, a private and a shared channel, two tabs, the Operations hub |
| [`src/bad/bad.team.json`](src/bad/bad.team.json) | A plan with the usual mistakes: the lint demo (16 errors, 2 warnings) |
| [`src/Invoke-TeamsIntegration.ps1`](src/Invoke-TeamsIntegration.ps1) | End to end: lint + storage map → `-Provision` (`-WhatIf`) → `-Check` |
| [`tests/MgTeams.Tests.ps1`](tests/MgTeams.Tests.ps1) | 28 Pester tests. The 9 tenant tests mock the **real** PnP cmdlets |

People in the plan are user names without a domain (`alex.demo`); `-UpnSuffix` adds the lab domain at run time, so no
tenant name is committed.

## Run it

```powershell
cd src
./Invoke-TeamsIntegration.ps1 -PlanPath ./bad/bad.team.json                 # 16 error(s), 2 warning(s)
./Invoke-TeamsIntegration.ps1 -PlanPath ./teams/purchasing.team.json        # 0 error(s), 0 warning(s), 3 SharePoint site(s)
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it the 9 tenant tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 28, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.1.0): **28 passed, 0 failed**; the two
commands above print exactly the counts shown.

In the lab (needs tenant; a team owner can create the team, a SharePoint Administrator is needed for the hub step; your
own Entra app for PnP with delegated Microsoft Graph permissions, listed below):

```powershell
$t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
        ClientId = '00000000-0000-0000-0000-000000000000'; UpnSuffix = 'contoso.com' }
./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Provision -WhatIf
./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Provision
./src/Invoke-TeamsIntegration.ps1 -PlanPath ./src/teams/purchasing.team.json @t -Check
```
One device-code sign-in to the admin center covers both the Graph calls (Teams) and the hub step.

## Permissions and licensing (what each part needs)

| Feature used | Licence / permission | Notes |
|---|---|---|
| Teams, team site, channels, tabs | Teams and SharePoint (the lab's Microsoft 365 E5) | No extra licence |
| Create the team | Graph delegated `Group.ReadWrite.All` | PnP docs for `New-PnPTeamsTeam` (`Team.Create` only with `-Template`) |
| Private or shared channel with an owner | `Group.ReadWrite.All` + `ChannelMember.ReadWrite.All` | PnP docs for `Add-PnPTeamsChannel -OwnerUPN` |
| Channel members, tabs | `ChannelMember.ReadWrite.All`; `Group.ReadWrite.All` | `Add-PnPTeamsChannelUser`, `Add-PnPTeamsTab` |
| Read back | `Group.Read.All`, `ChannelMember.Read.All` | `Get-PnPTeamsChannel`, `Get-PnPTeamsChannelFilesFolder`, `Get-PnPTeamsChannelUser` |
| Hub association | SharePoint Administrator | As in episode 7 |
| Not needed | SharePoint Premium, SharePoint Advanced Management | — |

Creating private channels is a policy: by default any team owner or member can, admins and team owners can restrict it
(Learn, private channels).

## The rules

| Rule | Checks | Source |
|---|---|---|
| TP001 | No display name; no owner; more than 100 owners | Teams limits: up to 100 owners per team |
| TP002 | Visibility isn't `Public` or `Private` | PnP `New-PnPTeamsTeam -Visibility` |
| TP003 | Channel name: empty, over 50 characters, a forbidden character (`~ # % & * { } + / \ : < > ? \| ' " ,` and `..`), a control character, a reserved word (`forms`, `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, `desktop.ini`, `_vti_`), a leading `_` or `.`, a trailing `.` | Teams limits "Channel names"; Graph create channel (50 characters) |
| TP004 | Two channels with the same name (case ignored) | the plan finds channels by name (this tool's convention) |
| TP005 | A channel called General (warning) | "Every team in Teams has a General channel" |
| TP006 | Channel type isn't Standard, Private or Shared | PnP `TeamsChannelType` |
| TP007 | A private or shared channel with no owner | `Add-PnPTeamsChannel -OwnerUPN` is required for both types |
| TP008 | A person in a private channel who isn't in the team | "Anyone ... can be added as a member of a private channel as long as they're existing members of the team" |
| TP009 | More than 1,000 channels, counting General | Teams limits: 1,000 per team, any mix of the three types |
| TP010 | Tab type not in PnP's `TeamTabType`; tab on a channel that isn't in the plan; Stream, Planner or Forms tab in a private or shared channel | Private channels: no Stream, Planner, Tasks by Planner and To Do, Forms; shared: tabs except Stream, Planner, Forms |
| TP011 | Tab with no URL, or neither `https://` nor a server-relative path | — |
| TP012 | Hub URL neither `https://` nor server-relative | — |
| TP013 | One owner only (warning) | convention, not a Learn rule |
| TL001 | The team doesn't exist | — |
| TL002 / TL003 | A channel is missing / has another type (it can't be converted: delete and create it again) | "private channels can't be converted to standard channels and vice versa" |
| TL004 | A person from the plan isn't a member of a private or shared channel | — |
| TL005 | A tab is missing, or points somewhere else | — |
| TL006 | A standard channel whose files folder isn't on the team site; a private or shared channel whose folder is (warning) | Teams-connected sites: standard channels share the parent site, the others have their own |
| TL007 | The team site isn't in the hub, or is in another one | Hub sites (episode 7) |

## Design choices
- **Count the sites.** `Get-MgChannelStorage` turns the plan into a table (channel, type, where the files go) and the
  entry script prints the number of SharePoint sites the team will use. The point of the episode is that this number is
  `1 + private + shared`, not `1`.
- **Never predict a channel folder URL.** Learn's app guidance says to always store the `driveId` and `itemId` that
  `GET /teams/{id}/channels/{id}/filesFolder` returns and not to hardcode library names or URLs. `Get-MgTeamState` asks
  for the folder of every channel (`Get-PnPTeamsChannelFilesFolder`) and compares the *site*, not a made-up path.
- **People by user name.** The plan lists `alex.demo`; the run adds the domain. Live members are compared by the part
  before the `@`, so `Alex.Demo@contoso.com` and `alex.demo` are the same person.
- **One owner per private or shared channel in the plan.** Graph: a shared channel can be created with only one owner;
  more owners are added afterwards. The plan has one `owner`, and `members` are added with
  `Add-PnPTeamsChannelUser -Role Member`.
- **Join the hub from the parent site.** Learn: associating the parent team site with a hub associates all its channel
  sites too, and the association is managed from the parent site (channel sites don't show it).
- **Find the team by display name, stop on two.** `Get-PnPTeamsTeam -Filter "displayName eq '…'"`; two teams with the
  same name are an error, because a name is the plan's key.

## What we learned / gotchas
- **A channel is a folder only in a standard channel.** Private and shared channels each have a site. Learn: people in
  the parent team and admins have no access to a private channel site unless they are also channel members, and its
  permissions can't be managed in SharePoint (they follow the channel's membership).
- **A channel's type is fixed.** Learn: a private channel can't be converted to another type. TL003 says "delete it and
  create it again" instead of trying.
- **The old 30-private-channel limit is gone.** Learn's private channels page now says private channels count toward
  the overall limit of up to 1,000 channels per team (standard, private and shared together; deleted channels count for
  30 days). Older articles still quote 30.
- **New private channels don't get a folder by default.** Learn (private channels): after the move to group compliance,
  newly created private channels are not created with a folder by default. See "Not verified yet".
- **The site can take a while.** Graph, create channel: if a private or shared channel's site fails to provision after
  five minutes, calling the files folder API triggers provisioning. `Wait-MgFilesFolder` retries that call.
- **Special characters break the files folder call.** Graph's create channel page warns that some characters in the name
  make `filesFolder` return an error; TP003 keeps them out.
- **PnP trap: channel ids must look like ids.** `TeamsChannelPipeBind` treats a string as an id only when it contains
  `@thread.` and has `:` as its third character (`19:…@thread.tacv2`); any other string is looked up by display name.
  The tests use realistic ids for that reason.
- **Pester traps with PnP pipe binds.** In a `-ParameterFilter`, `-Team`, `-Channel`, `-Site` and `-Identity` arrive as
  `PipeBind` objects: compare `$Channel.Id` and `$Site.Url`, not the object. `Add-PnPTeamsTab` has dynamic parameters
  (`-WebsiteUrl` for `SharePointPageAndList`, `-ContentUrl` for the others); Pester handles them.
- **PowerShell trap:** `[uri]::UnescapeDataString($x -replace 'a', '')` passes two arguments; wrap the `-replace` in
  parentheses.
- **Not verified yet (lab recording):** that `Get-PnPTeamsChannelFilesFolder` returns a folder for a freshly created
  private channel (Learn says no folder by default; the module treats a failure as "no folder", not a crash); that
  `Get-PnPTeamsChannelUser` returns `Email` for every member (TL004 compares it); that `New-PnPTeamsTeam` can be used
  right away for channels (the module reads the channels back before adding any); how long the team site takes before the
  hub step can find it (`-WaitSeconds`); whether a library URL as a `SharePointPageAndList` tab renders inside Teams
  (demo.md says what to check); whether the hub bar appears on the team site and on the channel sites. demo.md says what
  to record.

## References
- [Overview of Teams and SharePoint integration](https://learn.microsoft.com/sharepoint/teams-connected-sites) — when they get connected, standard / private / shared channel sites, parent site, channel site, who gets access
- [Manage settings and permissions when SharePoint and Teams are integrated](https://learn.microsoft.com/sharepoint/manage-teams-sharepoint-experiences) — channel sites and hub associations
- [Private channels in Microsoft Teams (IT admins)](https://learn.microsoft.com/microsoftteams/private-channels) — private channel sites, `TEAMCHANNEL#0`/`#1`, 1,000 channels overall, no Stream/Planner/Forms tabs, owners and members, creation policy, no folder by default, no conversion
- [Shared channels in Microsoft Teams](https://learn.microsoft.com/microsoftteams/shared-channels) — file access in shared channels
- [Overview of standard channels](https://learn.microsoft.com/microsoftteams/standard-channels) — all standard channels share one site, a folder each
- [Limits and specifications for Microsoft Teams](https://learn.microsoft.com/microsoftteams/limits-specifications-teams) — 1,000 channels per team, 100 owners, shared channel limits, channel name rules
- [Agents and tab apps for shared and private channels](https://learn.microsoft.com/microsoftteams/platform/build-apps-for-shared-private-channels) — `filesFolder`, always reuse `driveId`/`itemId`, don't hardcode URLs
- [Create channel (Microsoft Graph)](https://learn.microsoft.com/graph/api/channel-post) — 50-character display name, site provisioning note, one owner for a shared channel, special characters and `filesFolder`
- [Planning your SharePoint hub sites](https://learn.microsoft.com/sharepoint/planning-hub-sites) and the [episode 7 references](../07-hub-sites-navigation/README.md#references)
- [PnP PowerShell](https://pnp.github.io/powershell/) — `New-PnPTeamsTeam`, `Get-PnPTeamsTeam`, `Add-PnPTeamsChannel`, `Get-PnPTeamsChannel`, `Add-PnPTeamsChannelUser`, `Get-PnPTeamsChannelUser`, `Add-PnPTeamsTab`, `Get-PnPTeamsTab`, `Get-PnPTeamsChannelFilesFolder`, `Add-PnPHubSiteAssociation`, `Get-PnPTenantSite`
- Blog: [Integration with Teams — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-17-integration-with-teams-complete-guide-2026/) — the current article has no Teams-specific code (its steps only print messages); this folder is what to put in it
