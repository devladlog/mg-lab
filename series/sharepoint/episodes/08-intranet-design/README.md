# DEVLADLOG SharePoint #8 — Intranet design, as code

Episode 7 gave Contoso a hub: **Contoso Operations**, with Purchasing and Facilities. This episode builds the intranet
around it: a **home site**, the **global navigation** in the SharePoint app bar, **organization news** sites, an
**organization assets library** for the brand images, and a **tenant theme** whose colours are checked for contrast
before anybody sees them. All of it is in one **blueprint** (JSON) and a PowerShell module that:

- **lints the blueprint** before anything exists: the home site (a communication site, not a hub when other hubs exist,
  a 64×64 logo), organization news (up to 100 sites, the home site is one already), organization assets (up to 30
  libraries, all on one site, the thumbnail on that site), the global navigation (source, a 20×20 PNG logo, every hub
  linked, plus all the navigation rules of episode 7), images of 300 KB or less
- **checks a theme for contrast**: WCAG 2.x ratios computed in PowerShell for the palette's text pairs and for the new
  format's colour pairs; it passes the ten default themes on Learn and fails Learn's own "Custom Cyan" example
- **provisions** with PnP PowerShell, idempotently: adds the tenant theme and applies it, sets the home site, adds the
  organization news sites, creates the brand library, uploads the logos and registers it as an organization assets
  library, and builds the home site navigation that the app bar shows (reusing episode 7's navigation code)
- **reads it all back** and reports the drift: home site, news sites, asset libraries, theme palette, the home site's
  visitors, and the navigation tree

| Path | What it is |
|---|---|
| [`src/MgIntranet.psm1`](src/MgIntranet.psm1) | The module: `Get-MgContrastRatio`, `Get-MgPngSize`, `Test-MgTheme` (TH001–TH006), `Test-MgIntranet` (IN001–IN009 + the HN rules), `Test-MgIntranetLive` (IL001–IL006), `Invoke-MgTenantTheme`, `Invoke-MgHomeSite`, `Invoke-MgOrgNews`, `Invoke-MgOrgAssets`, `Invoke-MgGlobalNavigation`, `Get-MgIntranetState`. Imports `../07-hub-sites-navigation/src/MgHubNav.psm1` |
| [`src/intranet/contoso-intranet.json`](src/intranet/contoso-intranet.json) | The blueprint: home site `/sites/Intranet`, the Operations hub, one organization news site, the `BrandImages` library, the theme, one audience (*Purchasing Team*), a 12-node global navigation |
| [`src/intranet/contoso-operations.theme.json`](src/intranet/contoso-operations.theme.json) | The Contoso Operations theme (legacy palette format, what `Add-PnPTenantTheme` takes): primary `#0b5a8a`, 7.38:1 on white |
| [`src/intranet/assets/`](src/intranet/assets/) | Two PNGs generated for this sample: a 64×64 logo and a 20×20 global navigation logo |
| [`src/bad/bad-intranet.json`](src/bad/bad-intranet.json), [`src/bad/custom-cyan.theme.json`](src/bad/custom-cyan.theme.json), `src/bad/assets/logo-big.png` | The lint demo: a blueprint with the usual mistakes (6 errors, 6 warnings), Learn's "Custom Cyan" theme, a 512×512 logo |
| [`src/fixtures/learn-default-themes.json`](src/fixtures/learn-default-themes.json) | The colour pairs of the ten default SharePoint themes as published on Learn, to test the contrast check |
| [`src/Invoke-IntranetDesign.ps1`](src/Invoke-IntranetDesign.ps1) | End to end: lint (or `-ThemePath` for any theme file) → `-Provision` (`-WhatIf`) → `-Check` |
| [`tests/MgIntranet.Tests.ps1`](tests/MgIntranet.Tests.ps1) | 22 Pester tests. The 7 tenant tests mock the **real** PnP cmdlets |

## Run it

```powershell
cd src
./Invoke-IntranetDesign.ps1 -BlueprintPath ./bad/bad-intranet.json           # 6 error(s), 6 warning(s)
./Invoke-IntranetDesign.ps1 -BlueprintPath ./intranet/contoso-intranet.json  # 0 error(s), 0 warning(s)
./Invoke-IntranetDesign.ps1 -ThemePath ./fixtures/learn-default-themes.json  # ten themes ok, 0 errors
./Invoke-IntranetDesign.ps1 -ThemePath ./bad/custom-cyan.theme.json          # 2 error(s): 1.25:1
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it the 7 tenant tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 22, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.1.0): **22 passed, 0 failed**; the four
commands above print exactly the counts shown. The tests need the episode 7 folder next to this one.

In the lab (needs tenant; SharePoint Administrator for the tenant settings, owner of the home site for its navigation,
your own Entra app for PnP with delegated permissions, plus Microsoft Graph *Group.Read.All* if the blueprint names
audiences instead of giving group IDs):

```powershell
$t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
        ClientId = '00000000-0000-0000-0000-000000000000' }
./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Provision -WhatIf
./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Provision
./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Check
```
After `-Provision`, switch global navigation on in the browser: home site → Settings → Global navigation → Enable,
title, logo, source *Home site navigation*. The script builds the navigation; it doesn't flip that switch.

## Licensing (what each part needs)

| Feature used | Licence | Notes |
|---|---|---|
| Home site, organization news sites, organization assets library, tenant themes, global navigation | SharePoint (any plan; the lab's Microsoft 365 E5) | Home site, news and assets: SharePoint Administrator. Global navigation: site owner of the home site |
| Audience targeting on the global navigation | SharePoint (any plan) | As in episode 7 |
| Office template libraries (not used here) | Office 365 E3 or E5 for PowerPoint on the web; Microsoft 365 Apps 2002+ on the desktop | Learn: not in Word or Excel on the web. The blueprint uses an image library |
| Not built here | SharePoint app in Teams | Has its own licence rules (Learn: E, F or A licence to create the experience); the app bar's global navigation is the part it builds on |
| Not needed | SharePoint Premium, SharePoint Advanced Management | — |

## The rules

| Rule | Checks | Source |
|---|---|---|
| IN001 | Home site isn't a communication site (`SITEPAGEPUBLISHING#0`) | "A home site is a communication site"; "only one communication site can be set as the home site" |
| IN002 | Home site listed in `orgNewsSites` (warning) | "If you set a communication site as the home site, it's automatically configured as an organization news site" |
| IN003 | More than 100 organization news sites | "up to 100 organization news sites" |
| IN004 | More than 30 asset libraries; libraries on more than one site; a thumbnail on another site; an unknown type | "up to 30 organization asset libraries ... must be on the same site"; thumbnail "must be on the same site as the library"; types `ImageDocumentLibrary`, `OfficeTemplateLibrary` |
| IN005 | A hub missing from the global navigation (warning) | — (convention: global navigation "displays intranet navigational nodes and resources no matter where users are"; the hubs are how people reach the sites) |
| IN006 | The home site is a hub and there are other hubs (warning) | app bar: a home site that is a hub chooses between its site navigation and its hub navigation as the source, so the choice should be deliberate |
| IN007 | Logo not a PNG or the wrong size (warning) | global navigation logo 20×20 px, PNG, transparent background recommended; home site logo 64×64 px recommended |
| IN008 | An image above 300 KB (warning); a file that isn't there | modern portal limits: 300 KB per image |
| IN009 | Source isn't `homeSiteNavigation` or `hubOrGlobalNavigation`; a separate global navigation on a non-hub home site (warning: edited in the browser) | app bar: "Determine the global navigation source" |
| HN001–HN013 | The navigation rules of [episode 7](../07-hub-sites-navigation/), run on the global navigation | see episode 7 |
| TH001 | Neither a palette nor colour pairs; a missing palette slot | site theming JSON schema (the 22 slots of the legacy example) |
| TH002 | A value that isn't a 3- or 6-digit hex colour | schema: "6-digit or 3-digit hexadecimal RGB" |
| TH003 | Palette text pairs under 4.5:1: `neutralPrimary`/`neutralSecondary`/`themePrimary` on `white`, `white` on `themePrimary` | accessible text requirements: at least 4.5:1 (W3C G18) |
| TH004 | A colour pair (new format) under 4.5:1 | same |
| TH005 | More than 16 colour pairs | "up to 16 accent-and-background color pairs per theme" |
| TH006 | `isInverted` doesn't match the palette (warning) | schema: false for light themes, true for dark |
| IL001–IL006 | Live: home site differs; news site missing; asset library not registered; theme palette differs; *Everyone except external users* isn't a visitor of the home site; navigation drift (title, URL, audiences, order) | "Adding Everyone except external users as visitors is required"; users need read access to the home site to see global navigation |

## Design choices
- **Home site as a regular site, hubs linked from the global navigation.** The blueprint keeps `/sites/Intranet` out of
  the hub family and lists the Operations hub in the navigation (IN005/IN006). Learn offers both shapes (it even
  suggests a hub home site for organizations with many portals); this is a choice, not a rule, which is why IN006 is a
  warning that asks for a deliberate source.
- **The theme is a gate, not decoration.** `Test-MgTheme` runs before `Add-PnPTenantTheme`: a palette that fails
  contrast never reaches the tenant. The check covers the pairs that carry text (body, secondary, theme colour as
  link and as background for white text); it is a lint on the palette, not a replacement for looking at the pages.
- **Apply to the home site and the hub; let associated sites inherit.** `applyTo` lists `/sites/Intranet` and
  `/sites/Operations`. Sites associated with the hub follow the hub's theme (support article on hub sites; recorded
  in the lab, see demo.md).
- **Reuse, don't copy.** The global navigation is the home site navigation, built by the episode 7 functions
  (`Invoke-MgNavigationTree`: replace the tree only if it differs). Same rules, same drift check.
- **Images by size from the file, not from the name.** `Get-MgPngSize` reads width, height and byte size from the PNG
  header; no image library needed.
- **Read back after every run.** `-Check` compares the tenant with the blueprint (IL001–IL006).

## What we learned / gotchas
- **Learn's own theme example fails contrast.** The `Add-SPOTheme` page's "Custom Cyan" palette uploads fine, but
  `themePrimary` `#00ffff` on white is **1.25:1**, far under the 4.5:1 text minimum. A theme is accepted by the
  service whatever its contrast: nobody checks for you. The ten default themes all pass on every colour pair.
- **Global navigation isn't instant.** Learn: changes can take up to 24 hours to reach users, and edits to links may
  need the link deleted and added again when they error.
- **Read access to the home site is the price of global navigation.** Users who can't read the home site don't see
  the links (and the organization assets library needs the same: *Everyone except external users* as visitors,
  IL005).
- **One home site, a communication site.** Setting another replaces the first. Learn's best practice is to swap the
  home site into the root location **before** setting it; swapping afterwards can lose home site settings.
- **Hub or no hub changes the source choices.** A home site that is a hub offers *Home site navigation* or
  *Hub or global navigation*; one that isn't offers the site navigation or a separate set edited in the browser. The
  script provisions the home site navigation only (IN009 warns otherwise).
- **Enabling global navigation is a browser step** here: the script builds the navigation, you switch it on (title,
  logo, source) in the home site's Settings.
- **Same PowerShell traps as episode 7:** an `if` expression unrolls arrays (wrap in `@()`), and a Pester
  `-ParameterFilter` on an enum's first value never matches (0 is falsy).
- **Not verified yet (lab recording):** the exact shape of `Get-PnPOrgAssetsLibrary` output (the module reads
  `OrgAssetsLibraries[].LibraryUrl.DecodedUrl` and tolerates a plain string); whether `Set-PnPHomeSite -Force`
  is needed on a tenant with no home site; how long the theme takes to show on sites associated with the hub; which
  group the home site's visitors really contain on the lab tenant (IL005 compares the title *Everyone except external
  users*); whether a library URL comes back without its leading slash (handled by `Get-MgKey`). demo.md says what to
  check.

## References
- [Plan, build, and launch a SharePoint home site](https://learn.microsoft.com/sharepoint/home-site) — what a home site is (a communication site), organization news by default, global navigation, root site swap before setting the home site, 64×64 px logo, audience targeting, hub or not
- [Introduction to the SharePoint app bar](https://learn.microsoft.com/sharepoint/homesites/sharepoint-app-bar) — enable global navigation, 20×20 px PNG logo, source options for hub and non-hub home sites, read access to the home site, up to 24 hours, only one communication site can be the home site
- [Set-SPOHomeSite](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/set-spohomesite) — `-HomeSiteUrl`, `-Force`
- [Create an organization news site](https://learn.microsoft.com/sharepoint/organization-news-site) — up to 100 sites, the home site is one automatically
- [Create an organization assets library](https://learn.microsoft.com/sharepoint/organization-assets-library) — up to 30 libraries, same site, *Everyone except external users* as visitors, thumbnail on the same site, `ImageDocumentLibrary` / `OfficeTemplateLibrary`, private CDN by default, image picker "Your organization"
- [SharePoint site theming](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-theming/sharepoint-site-theming-overview) and [JSON schema](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-theming/sharepoint-site-theming-json-schema) — ten default themes, 16 colour pairs, palette slots, `isInverted`, the Teal example and the default themes' colour pairs; [PowerShell cmdlets](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-theming/sharepoint-site-theming-powershell) (`Add-SPOTheme`)
- [Site theme](https://learn.microsoft.com/sharepoint/site-theme) — brand center, colour pairs, built-in accessibility checker
- [Accessible text requirements](https://learn.microsoft.com/windows/apps/design/accessibility/accessible-text-requirements) — 4.5:1 (W3C WCAG G18)
- [SharePoint modern portal site limits](https://learn.microsoft.com/microsoft-365/enterprise/modern-portal-limits) — 300 KB per image, fewer than 100 navigation items
- [SharePoint limits](https://learn.microsoft.com/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits) — 500 child links per navigation level, 2,000 hubs
- [Planning your SharePoint hub sites](https://learn.microsoft.com/sharepoint/planning-hub-sites) and the [episode 7 references](../07-hub-sites-navigation/README.md#references)
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Add-PnPTenantTheme`, `Set-PnPWebTheme`, `Get-PnPTenantTheme`, `Set-PnPHomeSite`, `Get-PnPHomeSite`, `Add-PnPOrgNewsSite`, `Get-PnPOrgNewsSite`, `Add-PnPOrgAssetsLibrary`, `Get-PnPOrgAssetsLibrary`, `Get-PnPGroupMember`
- Blog: [Intranet Design — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-09-intranet-design-complete-guide-2026/)
