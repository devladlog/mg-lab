# DEVLADLOG Deep Dive #6 — Customer portal (Entra External ID + Power Pages + SharePoint)

> **About "Azure B2C" in the title.** The blog's Complete Guide is titled with Azure AD B2C. Microsoft Learn: *effective
> May 1, 2025, Azure AD B2C is no longer available to purchase for new customers*; existing customers keep using it,
> Microsoft supports it until at least May 2030, and B2C P2 was discontinued on March 15, 2026. A new portal, like
> Contoso's here, starts on the replacement: **Microsoft Entra External ID in an external tenant**, which Power Pages
> offers as a built-in identity provider. The folder name stays as planned; everything inside uses External ID.

Contoso's customers get a support portal. **Riley** (Northwind Traders) signs up with e-mail and password, sees her
own and her colleague **Alex**'s support requests, raises a new one and uploads photos that land in SharePoint.
**Taylor** (Adventure Works) sees only Adventure Works' requests. **Jordan**, who signed up but whom Contoso never
registered, sees nothing.

```
Customer ──► External ID (external tenant: email + password user flow) ──► Power Pages site (contact, web roles)
                                                                              │ Web API /_api + table permissions
                                                                              ▼
                                                   Dataverse: Support request ──► SharePoint: one folder per request
```

- **Authentication isn't authorization.** Anyone can sign up and becomes a contact with only *Authenticated Users*,
  which has **no** table permissions. Contoso registers customer contacts under their account and gives them the
  *Customer contacts* web role; at first sign-in Power Pages maps the account to that contact by e-mail.
- **Company visibility without anything to spoof.** The request has a *Raised by* lookup to Contact and **no account
  lookup**. "My requests" = Contact access (the only permission that can create). "My company's requests" =
  Account access on Contact (colleagues), with a child permission on their requests. A customer can't attach a
  request to another company because there is no such field, and can't bind another contact because the server
  checks Contact access on create.
- **Server-side rules only.** The page script has no filter: what the server returns *is* what the permissions allow.
  Web API is enabled for one table and eight named columns.

| Path | What it is |
|---|---|
| [`external-id/ExternalIdSetup.psm1`](external-id/ExternalIdSetup.psm1), [`Initialize-ExternalId.ps1`](external-id/Initialize-ExternalId.ps1) | Microsoft Graph PowerShell for the external tenant: app registration (reply URL, ID + access tokens), service principal, admin consent for `openid profile` (permission IDs looked up, not hard-coded), the sign-up/sign-in user flow (email + password), app ↔ flow link (refuses an app already linked elsewhere), then the Power Pages provider values. Idempotent, `-WhatIf` |
| [`portal/web-files/support-requests.js`](portal/web-files/support-requests.js) | Page script: FetchXML list via `/_api`, create with `mgl_Contact@odata.bind`, CSRF token from `shell.getTokenDeferred()`, null-safe mapping, HTML escaping, friendly 403 |
| [`portal/web-templates/my-requests.html`](portal/web-templates/my-requests.html) | Liquid web template for `/support/` |
| [`portal/table-permissions.json`](portal/table-permissions.json) | The authorization design as data (web role, table permission tree, page permission) |
| [`portal/site-settings.json`](portal/site-settings.json) | Web API settings (explicit columns), upload size |
| [`dataverse/support-request-table.json`](dataverse/support-request-table.json) | The *Support request* table |
| [`tests/`](tests) | `portal.test.mjs` (16) + `design.test.mjs` (15), Node built-in runner, no packages; `ExternalIdSetup.Tests.ps1` (10, Pester) |

## Test locally (no tenant)

```bash
npm test                                      # node --test: pass 31, fail 0 (no dependencies to install)
pwsh -NoProfile -c 'Invoke-Pester ./tests'    # Tests Passed: 10, Failed: 0
```

- `portal.test.mjs` runs the real page script with a recording `fetch`: the FetchXML (no filter, clamped page size),
  mapping when FetchXML omits nulls, formatted-value annotations, validation, the create body (contact bind, no
  account), the CSRF header on every call, `entityid` from the create response, 403 vs 400 messages, XSS escaping,
  and the page glue (load → submit → reload) on a minimal fake DOM.
- `design.test.mjs` checks Learn's Power Pages security guidance as rules over the design files: no Global access,
  nothing granted to built-in roles, exactly one Create path (Contact access), company visibility read-only, a
  Document Location child under every parent permission on requests, uploads only where the parent has Write, no
  Delete, Web API enabled for one table with explicit columns that equal the script's columns and exist in the table,
  choice values consistent between table, script and template, Liquid output escaped.
- `ExternalIdSetup.Tests.ps1` runs the module against an in-memory external tenant (tests only) that enforces the
  documented rules (an app needs a service principal and can be in one user flow): empty tenant → five *Added*,
  second run writes nothing, extra reply URL added without dropping the old one, partial consent completed (no second
  grant), app owned by another flow refused, non-https reply URL refused, `-WhatIf`, paging.

Tested with Node 22.23, PowerShell 7.6, Pester 6.2.0.

## Run it (needs the lab)

The full runbook is in [`demo.md`](demo.md): external tenant, table, contacts, SharePoint integration, Power Pages site,
identity provider (`Initialize-ExternalId.ps1` prints the values), web role, permissions, site settings, web file and
template. No Azure resources besides the external tenant itself (free core offer up to 50,000 MAU).

## What we learned / gotchas

- **B2C is end-of-sale for new customers** (see the note above). For this episode that changes the identity
  provider, not the portal design: Power Pages has a dedicated *Microsoft Entra External ID* provider (client ID,
  authority, metadata address; optional *Contact mapping with email*).
- **External tenants sign in at `<tenant>.ciamlogin.com`**, not `login.microsoftonline.com`; the metadata document is
  `https://<tenant>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration` (Learn, tokens overview). The
  script computes it from the tenant's initial domain and ID.
- **One user flow per app**, and the app needs a service principal before it can be linked. Our script checks every
  flow first and refuses to move an app silently.
- **`Webapi/<table>/fields` = `*` is deprecated** and requests fail until explicit columns are configured: list them
  (we test that the script uses exactly those).
- **Multi-level parent/child permissions + OData GET** is a documented known issue; Learn's workaround is FetchXML,
  which we use for the list. **FetchXML results omit null columns**, so the mapping treats every property as optional.
- **SharePoint documents need one Document Location child permission per parent permission** on the table; the
  parent needs Read + Append To (Write for uploads), and uploads only work on a form in *update existing record* mode.
  Default upload limit 10 MB (`SharePoint/MaxUploadSize`, max 50). Enabling SharePoint integration on the site needs
  a Global Administrator and restarts the site.
- **Built-in roles apply to everyone**: Learn's security best practices say to grant them only the minimum. We grant
  them nothing and protect `/support/` with a page permission (hiding a page from navigation doesn't secure it).
- **Power Pages sites start as trials** (90 days in production/sandbox environments, 30 in trial environments).
- **Not verified in the lab yet (needs tenant):** the relationship names in `table-permissions.json` (Dataverse
  defaults assumed); that the server rejects a create bound to a colleague's contact (the demo tests it and README
  will record the result); that `Prefer: odata.include-annotations` returns formatted values through the portal Web
  API (the script falls back to the choice labels); Liquid `user.parentcustomerid.name`; the exact Authority value the
  Endpoints blade shows; whether contact mapping by e-mail needs open registration on. Choice option values depend on
  the publisher prefix.

## References

- [Azure AD B2C end of sale (FAQ)](https://learn.microsoft.com/azure/active-directory-b2c/faq#azure-ad-b2c-end-of-sale) · [External ID FAQ: what's happening to Azure AD B2C, pricing (50,000 MAU free)](https://learn.microsoft.com/entra/external-id/customers/faq-customers) · [Plan your migration from B2C to External ID](https://learn.microsoft.com/entra/external-id/customers/plan-your-migration-from-b2c-to-external-id) · [External ID pricing](https://learn.microsoft.com/entra/external-id/external-identities-pricing)
- [Set up Microsoft Entra External ID with Power Pages](https://learn.microsoft.com/power-pages/security/authentication/entra-external-id) · [Create an external tenant](https://learn.microsoft.com/entra/external-id/customers/how-to-create-external-tenant-portal) · [Delete an external tenant](https://learn.microsoft.com/entra/external-id/customers/how-to-delete-external-tenant-portal) · [Tokens: ciamlogin.com endpoints and metadata](https://learn.microsoft.com/entra/identity-platform/security-tokens#token-endpoints-and-issuers)
- [Create authenticationEventsFlow (user flow)](https://learn.microsoft.com/graph/api/identitycontainer-post-authenticationeventsflows) · [Add includeApplication (one flow per app, needs a service principal)](https://learn.microsoft.com/graph/api/authenticationconditionsapplications-post-includeapplications) · [Create oAuth2PermissionGrant](https://learn.microsoft.com/graph/api/oauth2permissiongrant-post)
- [Portals Web API overview (site settings, deprecated wildcard, CSRF, known issue)](https://learn.microsoft.com/power-pages/configure/web-api-overview) · [Web API write operations (safeAjax, entityid, @odata.bind)](https://learn.microsoft.com/power-pages/configure/write-update-delete-operations) · [Web API read operations with FetchXML](https://learn.microsoft.com/power-pages/configure/read-operations) · [FetchXML: null columns aren't returned](https://learn.microsoft.com/power-apps/developer/data-platform/fetchxml/retrieve-data)
- [Table permissions (access types, parent/child)](https://learn.microsoft.com/power-pages/security/table-permissions) · [Security best practices](https://learn.microsoft.com/power-pages/security/security-best-practices) · [Manage SharePoint documents](https://learn.microsoft.com/power-pages/configure/manage-sharepoint-documents) · [Power Pages lifecycle (trial sites)](https://learn.microsoft.com/power-pages/admin/lifecycle)
- Blog: [Customer Portal: Secure External Access with Azure B2C, Power Pages and SharePoint — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-11-03-customer-portal-secure-external-access-azure-b2c-power-pages-sharepoint/)
