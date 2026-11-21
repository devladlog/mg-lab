# DEVLADLOG Deep Dive #12 — Modern Intranet Platform (SharePoint hub + Viva Connections + Teams + Power Automate)

Contoso (episodes 3, 4, 7 and 11) now needs a front door for its own people: one place for news, department pages and the
tools they use. The episode builds it **as code**: a SharePoint **hub site** with three department sites, a **home site**
that Viva Connections shows inside **Teams**, and a **Power Automate** approval for company news. Everything is described in
one contract file and provisioned by an idempotent PowerShell module. This episode does not repeat the purchase-request
platform; it only reuses the fictional company and the lab tenant.

```
contract/intranet.json ──► provision/Intranet.psm1 (PnP.PowerShell)                       Microsoft 365 tenant
   names, aliases,           1. site script + site design  (header, mega menu, sharing off, News Requests list)
   navigation, statuses      2. sites: contoso-home, -hr, -it, -ops   (communication sites, created with the design)
        │                    3. register contoso-home as hub site
        │                    4. associate the three departments with the hub
        │                    5. hub navigation (top bar of the hub site)
        │                    6. home site = contoso-home (draft, Viva Connections default start)  ──► Teams: pin the app
        └──► tests, health check and flow/news-approval.definition.json read the same file
```

- **One contract, many readers.** `contract/intranet.json` holds the aliases, titles, navigation and the News Requests
  statuses. The provisioning module, the read-only health check, the flow definition and the tests all read it, so a rename
  that breaks one of them fails a test.
- **Idempotent and honest about it.** Every step first asks whether the thing exists (`Exists`), honours `-WhatIf`, and the
  module never signs in and never stores a credential. Run it twice: the second run reports `Exists` on every line.
- **Hub association from PowerShell, not from the site script.** The site-script verb `joinHubSite` carries a hub site id,
  which is different in every tenant. The module uses `Add-PnPHubSiteAssociation` and a test rejects `joinHubSite`.
- **Viva Connections is the home site, seen in Teams.** `Set-PnPHomeSite` makes the hub the home site; the Teams admin center
  pins the app. Both switches (`DraftMode`, `VivaConnectionsDefaultStart`) are passed explicitly, never left to the defaults.
- **News approval with standard connectors only.** SharePoint "when an item is created" → Approvals "start and wait for an
  approval" → SharePoint "update item" with the outcome. No premium licence for requesters or approvers.

| Path | What it is |
|---|---|
| [`contract/intranet.json`](contract/intranet.json) | The single source of truth (fictional names only) |
| [`site-scripts/intranet-site.json`](site-scripts/intranet-site.json) | Site script: branding, external sharing off, the `News Requests` list (Summary, Department, NewsStatus, NewsMessage), a navigation link |
| [`provision/Intranet.psm1`](provision/Intranet.psm1) | `Test-IntranetContract`, `Test-IntranetSiteVerbs`, `Publish-IntranetSiteDesign`, `Invoke-IntranetProvisioning`, `Test-IntranetHealth` |
| [`provision/Initialize-Intranet.ps1`](provision/Initialize-Intranet.ps1) | Entry point: connects (browser sign-in, your own app registration), builds, `-WhatIf` supported |
| [`provision/Test-Intranet.ps1`](provision/Test-Intranet.ps1) | Read-only health check, exit code 1 when a check fails |
| [`flow/news-approval.definition.json`](flow/news-approval.definition.json) | Reference definition of the approval flow, written by hand (see "Not verified") |
| [`tests/Intranet.Tests.ps1`](tests/Intranet.Tests.ps1), [`tests/Flow.Tests.ps1`](tests/Flow.Tests.ps1) | 25 + 7 Pester tests |

## Test locally (no tenant, no sign-in)

Needs PowerShell 7.4+, Pester 5 or later and the `PnP.PowerShell` module (3.1.0 was used). The tests import PnP.PowerShell so
that Pester copies the **real cmdlet signatures** into each mock: a misspelt or unknown parameter in the module fails the test.

```bash
cd series/deep-dive/episodes/12-modern-intranet-platform-sharepoint-viva-teams-p
pwsh -NoProfile -c 'Invoke-Pester ./tests'      # expect: Tests Passed: 32, Failed: 0 (about 50 s)
```

| Area | Tests | What they prove |
|---|---|---|
| Contract | 5 | Valid contract passes; bad or duplicate aliases, a home site that is not the hub, unknown or non-https navigation, a department missing from the navigation are all reported |
| Site script | 4 | Only verbs listed on Learn, valid enum values, no `joinHubSite`; the list columns and the three statuses equal the contract; fields have fixed ids so a re-run does not duplicate columns |
| Provisioning (mocked PnP) | 9 | Empty tenant in a safe order; every site a communication site created with the design and `-Wait`; hub navigation written on the hub site with the external link marked; home site draft + Viva start; **second run changes nothing**; half-built intranet completed with only the missing pieces; hub children returned as URLs or as objects; `-WhatIf` changes nothing; an invalid contract stops before any tenant call |
| Health check | 5 | Passes on a healthy intranet; fails for a wrong home site, a department that left the hub, an unplanned site in the hub, a missing or wrong link; the function contains no state-changing cmdlet |
| Entry scripts | 2 | Parse, take `TenantName` and `ClientId`, `Initialize-Intranet.ps1` supports `-WhatIf`; no secret or real tenant text |
| Flow | 7 | Only the SharePoint and Approvals connectors; every `runAfter` target exists; every column used is in the contract; only contract statuses are written; approval comes before any change; list and site are parameters; no real address |

The mocks keep an in-memory "tenant", so the tests also check **order** (design before sites, hub before associations) and
**counts** (hub registered once, only missing children associated).

## Deploy and run (needs a Microsoft 365 tenant)

```powershell
# one-time: an Entra app registration you own for PnP.PowerShell (permissions and redirect: see the PnP authentication
# article in References), then, as a SharePoint administrator:
./provision/Initialize-Intranet.ps1 -TenantName <tenant> -ClientId <app id> -WhatIf   # the plan
./provision/Initialize-Intranet.ps1 -TenantName <tenant> -ClientId <app id>           # build
./provision/Initialize-Intranet.ps1 -TenantName <tenant> -ClientId <app id>           # again: every line says Exists
./provision/Test-Intranet.ps1       -TenantName <tenant> -ClientId <app id>           # read-only check
```

Then pin the app in Teams and build the flow in the designer: [`demo.md`](demo.md) has the steps. The contract's `tenantName`
is `contoso` (fictional); pass `-TenantName` for the real one.

## What we learned / gotchas

- **`-WhatIf` is inherited by helper functions.** Under `-WhatIf`, a property shortcut such as `ForEach-Object alias` prints
  "What if: Retrieve the value for property" and returns nothing, so contract validation saw no sites and reported a valid
  contract as broken. The module uses script blocks (`ForEach-Object { $_.alias }`) and a test runs the whole thing with `-WhatIf`.
- **`,$array` hides rows from the pipeline.** The health check first returned `,$rows.ToArray()`: the tests could not filter the
  rows with `Where-Object`. It now returns the rows themselves.
- **Mocks with real signatures catch typos, but need the real types.** Mocked cmdlets take `-Connection` as `PnPConnection`, a
  `PSCustomObject` is rejected; the tests build an empty instance with `GetUninitializedObject`. `-Site` arrives as a
  `SitePipeBind`, so mocks read `$Site.Url`, not `"$Site"`.
- **Cmdlets return URLs or objects.** `ConvertTo-SiteUrl` accepts both and compares without case and trailing slash (the return
  type of `Get-PnPHubSiteChild` is not documented; a test feeds both shapes).
- **The hub is not instant.** Learn: hub registration changes can take 2 to 4 hours to show. The health check reports a missing
  hub with that hint.
- **Plan inside the limits.** Learn planning guidance: 2,000 hub sites per tenant; recommended at most 100 hub navigation links
  (500 is the technical limit); no more than 99 sites in the Sites web part. The contract test warns above 100 links.
- **A home site must be a communication site**, and one Viva Connections experience is included with E, F or A licences; more
  than one (up to 50) needs a Viva Suite or Viva Communications and Communities licence. The contract has one.
- **Home site management is moving to the SharePoint admin center** (Settings > Home sites); the Teams admin center is still
  where the app is pinned (Setup policies > Pinned apps). See "Not verified" for what that means for `Set-PnPHomeSite`.
- **Defaults are not your intent.** The `Set-PnPHomeSite` documentation lists `DraftMode` and `VivaConnectionsDefaultStart`
  with default true, so both are passed explicitly from the contract.
- **PnP.PowerShell needs your own app registration:** the PnP authentication article says to create your own application registration first and pass its client id with `-ClientId`. Nothing is stored.

## Not verified in the lab yet

Everything below needs the lab tenant; nothing here was run against Microsoft 365 when this was written. Record the outcome of
each after the first run.

- The whole of `Invoke-IntranetProvisioning` against a real tenant (cmdlet behaviour, timing, the hub delay).
- Whether `Set-PnPHomeSite` still works unchanged now that home site management is moving to the SharePoint admin center, and
  that `-DraftMode` corresponds to the Draft state shown for the experience there.
- The site script applied by a real site design: the exact result of `setSiteBranding`, the `News Requests` list and its
  `NewsStatus` choice field (only the JSON and its schema verbs are checked offline).
- `Get-PnPHubSiteChild` return type on a real hub.
- **The flow definition has not been imported anywhere.** Power Automate has no plain "import JSON" for a hand-written
  definition: build the flow in the designer (steps in `demo.md`), export it, replace `flow/news-approval.definition.json`
  with the export and re-run `Flow.Tests.ps1`. How the approval request is delivered (Approvals app in Teams, e-mail) is
  something to observe on camera, not assumed. A Teams post action was left out on purpose because its parameters were
  not verified.
- Pinning the app in Teams and how long a new pin policy takes to reach a user.

## References

- [Planning your SharePoint hub sites (limits, navigation, permissions)](https://learn.microsoft.com/sharepoint/planning-hub-sites)
- [SharePoint site design and site script overview](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-overview) · [Site script JSON schema (verbs)](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-json-schema) · [Site design and PnP provisioning](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-pnp-provisioning)
- [Set up Viva Connections and home sites (prerequisites, home sites in the SharePoint admin center, pin the app in Teams)](https://learn.microsoft.com/sharepoint/homesites/set-up-admin-center) · [SharePoint app in Teams / Viva Connections overview](https://learn.microsoft.com/sharepoint/homesites/sharepoint-app-in-teams-overview)
- [Get started with approvals (Power Automate)](https://learn.microsoft.com/power-automate/get-started-approvals) · [SharePoint and Power Automate](https://learn.microsoft.com/power-automate/sharepoint-overview)
- PnP.PowerShell (community docs): [Set-PnPHomeSite](https://pnp.github.io/powershell/cmdlets/Set-PnPHomeSite.html) · [Register-PnPHubSite](https://pnp.github.io/powershell/cmdlets/Register-PnPHubSite.html) · [Add-PnPHubSiteAssociation](https://pnp.github.io/powershell/cmdlets/Add-PnPHubSiteAssociation.html) · [Add-PnPSiteDesign](https://pnp.github.io/powershell/cmdlets/Add-PnPSiteDesign.html) · [Authentication](https://pnp.github.io/powershell/articles/authentication.html)
- Blog: [Modern Intranet Platform — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-01-13-modern-intranet-platform-sharepoint-viva-teams-power-platform/)
