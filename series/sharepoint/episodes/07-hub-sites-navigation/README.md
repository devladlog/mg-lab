# DEVLADLOG SharePoint #7 — Hub sites and navigation, as code

The Contoso Purchasing site ([episode 3](../03-modern-sites-pages/)) has its own navigation, its Supplier Documents
library ([episode 4](../04-document-management/)), its permissions ([episode 5](../05-permissions-governance/)) and its
search schema ([episode 6](../06-search-metadata/)). It still sits alone. In this episode it joins a family: a new
**Contoso Operations** hub, with Purchasing and a new **Contoso Facilities** site associated, and one shared hub
navigation. Everything is in a **hub plan** (JSON) and a PowerShell module that:

- **lints the plan** before anything exists: the hub settings (who may associate, join approval, hide the name without
  a logo, site template ID, parent hub) and the hub navigation against Learn's limits (three levels, 500 links per
  level, 100 recommended in total, 10 audiences per link, labels need links, pages not files, associated sites linked,
  private sites targeted)
- **checks the hub hierarchy** of the tenant (hub-to-hub associations: three levels, no cycles, 2,000 hubs)
- **provisions** with PnP PowerShell, idempotently: registers the hub with who may associate, sets only the properties
  that differ, associates the sites (moving a site from another hub only with `-Move`), turns on navigation audience
  targeting and the mega menu, and builds the hub navigation with audiences resolved to Entra group IDs
- **reads it all back** and reports the drift: hub settings, associated sites, the navigation tree with audiences, the
  web settings

Episode 8 imports this module for the global navigation in the SharePoint app bar.

| Path | What it is |
|---|---|
| [`src/MgHubNav.psm1`](src/MgHubNav.psm1) | The module: `Test-MgHubPlan` (HB001–HB007), `Test-MgNavigation` (HN001–HN013), `Test-MgHubHierarchy` (HH001–HH004), `Compare-MgNavigation`, `Test-MgHubLive` (HL001–HL005), `Resolve-MgAudience`, `Invoke-MgHubRegistration`, `Invoke-MgHubAssociation`, `Get-MgLiveNavigation`, `Invoke-MgNavigationTree`, `Invoke-MgHubNavigation`, `Get-MgHubState` |
| [`src/hub/operations.hub.json`](src/hub/operations.hub.json) | The hub plan: Contoso Operations (`/sites/Operations`), who may associate (*Operations Site Owners*), two associated sites, two audiences (*Purchasing Team*, *Facilities Team*), a three-level mega menu with 15 nodes |
| [`src/hub/operations-logo.png`](src/hub/operations-logo.png) | A 64×64 PNG for the hub logo (generated for this sample) |
| [`src/bad/bad.hub.json`](src/bad/bad.hub.json) | A plan with the usual mistakes: the lint demo (10 errors, 8 warnings) |
| [`src/fixtures/tenant-hubs.json`](src/fixtures/tenant-hubs.json) | Three fictional hubs (Global → Europe → Portugal) shaped like `Get-PnPHubSite` output, for the hierarchy check |
| [`src/Invoke-HubNavigation.ps1`](src/Invoke-HubNavigation.ps1) | End to end: lint (+ `-HubsPath` hierarchy) → `-Provision` (admin center + hub site, `-WhatIf`, `-Move`) → `-Check` |
| [`tests/MgHubNav.Tests.ps1`](tests/MgHubNav.Tests.ps1) | 27 Pester tests. The 8 tenant tests mock the **real** PnP cmdlets |

## Run it

```powershell
cd src
./Invoke-HubNavigation.ps1 -PlanPath ./bad/bad.hub.json                                            # 10 error(s), 8 warning(s)
./Invoke-HubNavigation.ps1 -PlanPath ./hub/operations.hub.json -HubsPath ./fixtures/tenant-hubs.json  # 0 error(s), 0 warning(s)
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it the 8 tenant tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 27, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2): **27 passed, 0 failed** with PnP.PowerShell 3.5.0 and
again with 3.1.0.

In the lab (needs tenant; SharePoint Administrator for the hub and the associations, hub site owner for the
navigation, your own Entra app for PnP with delegated permissions, plus Microsoft Graph *Group.Read.All* if the plan
names audiences instead of giving group IDs):

```powershell
$t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
        ClientId = '00000000-0000-0000-0000-000000000000' }
./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Provision -WhatIf
./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Provision
./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Check
```

## Licensing (what each part needs)

| Feature used | Licence | Notes |
|---|---|---|
| Hub sites, hub navigation, hub-to-hub association, mega menu | SharePoint (any plan; the lab's Microsoft 365 E5) | Registering a hub and associating sites: SharePoint Administrator (admin center or PowerShell) |
| Audience targeting on navigation links | SharePoint (any plan) | Microsoft Entra security groups or Microsoft 365 groups; dynamic groups are only partially supported for some tenants (support article) |
| Join approval (`requiresJoinApproval`) | Power Automate (standard) | Not used: sites can only join when an active approval flow exists (PnP help); HB003 warns |
| Not needed | SharePoint Premium, SharePoint Advanced Management | — |

## The rules

| Rule | Checks | Source |
|---|---|---|
| HB001 | Hub URL isn't a site collection (`/sites/Name`, `/teams/Name`) | — |
| HB002 | `hideNameInNavigation` without `logoUrl` | "You can hide the hub site name as long as you have selected a logo" (support: set up your hub site) |
| HB003 | `requiresJoinApproval` (warning) | PnP `Set-PnPHubSite`: sites join only if there is an active approval flow |
| HB004 | Nobody named in `canAssociate` (warning) | "If you leave the People who can associate sites with this hub box empty, any user can associate their site" |
| HB005 | `siteDesignId` not a GUID, or the empty GUID | — |
| HB006 | An association listed twice, the hub itself, or the parent hub | "an individual site can be associated with only one hub" |
| HB007 | The hub is its own parent | — |
| HN001 | More than 3 levels | "Both cascading and mega menus support up to three levels" |
| HN002 | More than 500 links at one level | "all navigation types (site, hub, global, and footer) are limited to 500 child links at each level" |
| HN003 | More than 100 links in total (warning) | modern portal limits: fewer than 100 items in site navigation |
| HN004 | A label with no links below it (warning) | "A label should always have at least one link below" |
| HN005 | Audiences with targeting off; more than 10; an audience the plan doesn't declare | support article: 10 groups per link; site owner must enable targeting |
| HN006 | A child targeted outside its parent's audiences (warning) | "When audience targeting is applied to a parent link, audience targeting also gets applied to the sub-links" |
| HN007 | Link to a document (warning) | "Link to pages, not individual documents" |
| HN008 | Associated site not linked (warning) | "Associating with the hub does not automatically add the site to the hub navigation" |
| HN009 | Private associated site linked for everyone (warning) | planning guide: use audience targeting or label the link (private) |
| HN010 | The same label twice under one parent (warning) | "clear, mutually exclusive labels" |
| HN011 | `openInNewTab` outside QuickLaunch (warning) | PnP `Add-PnPNavigationNode`: only works on QuickLaunch (SharePoint API limitation) |
| HN012 | URL with a fragment (`#`) | PnP `Add-PnPNavigationNode`: "Fragments are not supported" |
| HN013 | Empty title | — |
| HH001 | A hub at level 4+ of hub-to-hub associations | "Content on sites beyond level 3 won't appear in search results" |
| HH002 | Hub-to-hub cycle | — |
| HH003 | More than 2,000 hubs | "An organization can have up to 2,000 hub sites" |
| HH004 | Planned parent hub isn't a hub | — |
| HL001–HL005 | Live: hub missing or settings differ; association missing; extra associated site (warning); navigation drift (title, URL, audiences, order); audience targeting / mega menu settings differ | — |

## Design choices
- **Plan by URL and group name, not by ID.** URLs are server-relative and the tenant is a parameter; audiences are
  group names resolved with `Get-PnPEntraIDGroup` at run time (or a GUID in the plan, when Graph permissions aren't
  available). The same plan works in any tenant.
- **Hub navigation = the hub site's TopNavigationBar.** PnP's own hub navigation copy sample reads and writes
  `-Location TopNavigationBar` on the hub site; we do the same.
- **Replace, don't patch, the navigation.** Navigation is read top to bottom, so order matters. If the live tree
  differs from the plan in any way (title, URL, audiences, order), the top-level nodes are removed (their children go
  with them) and the tree is added again. If it matches, nothing is touched. Links outside the hub site collection
  are added with `-External`.
- **Two connections.** Hub registration, association and `Get-PnPHubSite` need the admin center; the navigation and
  `Set-PnPWeb` need the hub site.
- **Never move a site silently.** A site already in another hub is reported and skipped; `-Move` removes the old
  association first. A site that is itself a hub is never associated as a plain site (use `parentHubUrl`, which calls
  `Add-PnPHubToHubAssociation`).
- **Read back after every run.** `-Check` compares the tenant with the plan, so a tab renamed in the browser shows up
  as HL004 instead of surviving forever.

## What we learned / gotchas
- **Association adds no link and no access.** Learn: associating doesn't add the site to the hub navigation, and
  hub association doesn't change permissions on either side. HN008 is a warning on every associated site that nobody
  linked.
- **Audience targeting is a filter, not security.** Learn (SharePoint app in Teams audience targeting): it "isn't a
  security measure"; editors see every link while editing. Targeting a parent applies to all its sub-links, so a child
  aimed at a group outside the parent's audience is only seen by people in both (HN006).
- **Targeting must be switched on per site.** Without *Enable site navigation audience targeting*
  (`Set-PnPWeb -NavAudienceTargetingEnabled`), audiences on links do nothing: everyone sees the link (HN005).
- **`openInNewTab` is silently ignored outside QuickLaunch** (PnP help). The hub navigation is TopNavigationBar.
- **Join approval needs a flow.** `Set-PnPHubSite -RequiresJoinApproval` without an active approval flow means sites
  can't join at all.
- **`RequiresJoinApproval`, `HideNameInNavigation` and `EnablePermissionsSync` are switches in PnP** but Booleans in
  `Set-SPOHubSite`; the module passes `-Name:$false` to turn them off.
- **PowerShell: an `if` expression unrolls arrays.** `$x = if (...) { $array } else { $other }` turned a one-item array
  into a string and an empty one into `$null`, which then failed under `Set-StrictMode` (`.Count` on `$null`).
  Wrapping it in `@(...)` fixed it.
- **Pester: `-ParameterFilter { $Location }` never matched** because `TopNavigationBar` is the enum's first value
  (0, falsy). The tests filter on `$Id` instead.
- **Not verified yet (lab recording):** that a label (node without a link) is stored with the URL
  `http://linkless.header/` (what the modern editor is known to store; not documented on Learn — if
  `Add-PnPNavigationNode` refuses it or the label renders as a link, fix `$script:LabelUrl`); whether
  `Get-PnPHubSiteChild` returns URLs or objects (the module accepts both); whether `-External` is needed for links to
  other site collections; which default nodes a new communication site has in its TopNavigationBar; how long
  navigation audience targeting takes to apply for a newly added group member. demo.md says what to check.

## References
- [Planning your SharePoint hub sites](https://learn.microsoft.com/sharepoint/planning-hub-sites) — what associating does and doesn't do, one hub per site, 2,000 hubs, three levels of hub navigation, private sites and audience targeting, 100 links / 99 sites in the Sites web part, home site as a hub or not
- [Create a hub site in SharePoint](https://learn.microsoft.com/sharepoint/create-hub-site) — SharePoint Administrator, empty "people who can associate" means anyone, associated sites can't become hubs, no limit on associated sites
- [Associate a hub site to another hub](https://learn.microsoft.com/sharepoint/hub-to-hub-association) — three levels, no permission change, web parts keep the original parent hub
- [Plan and implement SharePoint site navigation](https://learn.microsoft.com/sharepoint/plan-navigation-modern-experience) — mega and cascading menus, three levels, labels and links, link to pages not documents, clear labels
- [SharePoint limits](https://learn.microsoft.com/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits) — 500 child links per level for site, hub, global and footer navigation; 2,000 hubs
- [SharePoint modern portal site limits](https://learn.microsoft.com/microsoft-365/enterprise/modern-portal-limits) — fewer than 100 items in site navigation
- [Use audience targeting to personalize the SharePoint app in Teams](https://learn.microsoft.com/sharepoint/homesites/use-audience-targeting-sharepoint-app-in-teams) — audience targeting isn't a security measure; Entra security, Microsoft 365 and dynamic groups
- Support: [Target navigation, news, files, links and web parts to specific audiences](https://support.microsoft.com/office/target-navigation-news-files-links-and-web-parts-to-specific-audiences-33d84cb6-14ed-4e53-a426-74c38ea32293) — enable per site, 10 groups per link, parent targeting applies to sub-links, editors see all links
- Support: [Set up your SharePoint hub site](https://support.microsoft.com/office/set-up-your-sharepoint-hub-site-e2daed64-658c-4462-aeaf-7d1a92eba098) — theme inheritance, hide the name only with a logo, join approval flows
- [Set-SPOHubSite](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/set-spohubsite) — Title, LogoUrl, Description, SiteDesignId, RequiresJoinApproval, HideNameInNavigation, EnablePermissionsSync
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Register-PnPHubSite -Principals`, `Set-PnPHubSite`, `Grant-PnPHubSiteRights`, `Add-PnPHubSiteAssociation`, `Remove-PnPHubSiteAssociation`, `Add-PnPHubToHubAssociation`, `Get-PnPHubSite`, `Get-PnPHubSiteChild`, `Get-PnPTenantSite`, `Add-PnPNavigationNode -AudienceIds -External`, `Get-PnPNavigationNode`, `Remove-PnPNavigationNode`, `Set-PnPWeb -NavAudienceTargetingEnabled -MegaMenuEnabled`, `Get-PnPEntraIDGroup`; [copy hub navigation sample](https://pnp.github.io/script-samples/samples/spo-copy-hubsite-navigation/) (TopNavigationBar on the hub site)
- Blog: [Hub Sites & Navigation — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-02-hub-sites-navigation-complete-guide-2026/)
