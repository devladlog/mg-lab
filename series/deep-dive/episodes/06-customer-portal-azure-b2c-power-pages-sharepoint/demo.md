# Demo shot list — DEVLADLOG Deep Dive #6, Customer portal (Entra External ID + Power Pages + SharePoint)

Code and test scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 31 Node tests + 10 Pester tests pass.

> **Why not Azure AD B2C?** The blog title says B2C. Learn: effective 1 May 2025 Azure AD B2C is no longer available
> to purchase for new customers (existing tenants supported until at least May 2030; B2C P2 discontinued 15 March 2026).
> The lab tenant is a new customer, so the episode uses the replacement: **Microsoft Entra External ID in an external
> tenant**, which Power Pages supports as a built-in identity provider. The folder keeps its original name.

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge (normal window for admin work, **InPrivate** windows for each
customer), a terminal for `pwsh`. **No Hyper-V VM is needed.**

**Azure** — resource group `rg-mglab-deep-dive-06` (West Europe resource group; the tenant's data location is
chosen in the wizard, pick Europe)

| Resource | SKU | Estimated cost |
|---|---|---|
| Microsoft Entra External ID **external tenant** `contosocustomers` (created from the Entra admin center and linked to the lab subscription / this resource group) | External ID core, MAU billing | **€0**: the core offer is free for the first 50,000 monthly active users; the demo has 4. No add-ons (no SMS MFA, which is charged). |

No other Azure resources. The €30 budget is not touched.

**Microsoft 365 lab tenant (workforce)**
- **Power Platform environment `DEV`** (Dataverse): table *Support request*, the Power Pages site. The site is created
  as a **trial site** (Learn: trial sites expire after 90 days in production/sandbox environments, 30 days in trial
  environments); nothing is converted to production. Making the site needs the environment's System Administrator
  or maker role (Lab Admin). If Lab Admin is asked for a Power Apps licence when opening the *Portal Management* /
  *Power Pages Management* app, start the **self-service Power Apps Premium trial** (there are no spare premium
  licences in the lab). Customers need no licence of any kind.
- **SharePoint:** new site `/sites/customer-docs`, used as the default site of the environment's server-based
  SharePoint integration (created in setup, deleted in tear-down).
- **Lab Admin** is Global Administrator (needed to enable SharePoint integration on the site and to create the
  external tenant).

**Fictional customers** (external tenant accounts created by sign-up; their e-mail addresses are lab mailboxes so the
verification codes can be read; mask the domain):

| Person | Account (contact) in Dataverse | Web role | Role in the demo |
|---|---|---|---|
| Riley Demo | contact at **Northwind Traders** | Customer contacts | signs up, raises a request, uploads a document |
| Alex Demo | contact at **Northwind Traders** | Customer contacts | colleague: one existing request |
| Taylor Demo | contact at **Adventure Works** | Customer contacts | other customer: one existing request, must not see Northwind's |
| Jordan Demo | *no contact registered* | — | signs up, must see nothing |

**Local tools:** PowerShell 7.4+ with `Microsoft.Graph.Authentication`; Node 22 only to run the tests.

## Setup (off camera)

1. **Tests**
   ```bash
   cd series/deep-dive/episodes/06-customer-portal-azure-b2c-power-pages-sharepoint
   npm test                                          # pass 31
   pwsh -NoProfile -c 'Invoke-Pester ./tests'        # Tests Passed: 10
   ```
2. **External tenant**: Entra admin center (workforce, Lab Admin) → Manage tenants → Create → **External**, name
   *Contoso customers*, domain `contosocustomers` (or the next free one), location Europe, subscription = lab,
   resource group `rg-mglab-deep-dive-06`. Wait until it's ready, switch to it, note the **tenant ID**.
3. **Dataverse table** in `DEV` (solution `Customer portal`, publisher prefix `mgl`): create *Support request* exactly
   as `dataverse/support-request-table.json` — Title (primary, 200), Description (multiline, 2000), Reference
   (autonumber `SR-{SEQNUM:5}`), Category and Status (choices; if your option values differ from the file, update the
   file and re-run `npm test`), **Raised by** = lookup to Contact (schema name `mgl_Contact`). **No account lookup.**
   Turn on **document management** for the table (Advanced settings → Document management settings) after step 5.
   Create the main form with Title, Category, Status, Description and a **Document Locations** subgrid (view
   *Active Document Locations*).
4. **Accounts and contacts** (model-driven app or Power Pages Management → Contacts): accounts *Northwind Traders*,
   *Adventure Works*; contacts Riley Demo and Alex Demo (Northwind, company = parent account), Taylor Demo
   (Adventure Works), each with the **exact e-mail** they will sign up with. One existing request per contact for
   Alex and Taylor (create them in the model-driven app with *Raised by* set).
5. **SharePoint integration**: create the site *Customer docs*; Power Platform admin center → `DEV` → Settings →
   Integration → **Document management settings / server-based SharePoint integration** to that site. Then
   (after the Power Pages site exists, step 6) Power Platform admin center → Power Pages → the site → **SharePoint
   Integration = Yes**, accept the consent prompt (Learn: Global Administrator; the site restarts for a few minutes).
6. **Power Pages site** `Contoso support` (template: blank or *Starter layout*), in `DEV`. Note its URL.
7. **Identity provider**: design studio → Security → Identity providers → **Microsoft Entra External ID** →
   Configure, name *Contoso customers*, **copy the Reply URL**, keep the tab open. Then in a terminal:
   ```powershell
   ./external-id/Initialize-ExternalId.ps1 -TenantId <external tenant ID> -ReplyUrl <reply URL> -WhatIf
   ./external-id/Initialize-ExternalId.ps1 -TenantId <external tenant ID> -ReplyUrl <reply URL>
   ```
   (sign in as the **external tenant's** admin; run twice, the second run shows `Exists` for all five steps).
   Paste Client ID, Authority and Metadata address into the wizard; compare Authority with the app's **Endpoints**
   blade and use the blade's value if it differs (write it in README). Additional settings: **Contact mapping with
   email = On**, External logout = On. Confirm. Restart the site from the admin center if the button doesn't appear.
8. **Web role, table permissions, page**: Power Pages Management → Web Roles → new **Customer contacts** (not the
   authenticated or anonymous role). Add it to Riley, Alex and Taylor's contacts. Design studio → Security → Table
   permissions: create the tree in `portal/table-permissions.json` exactly (child permissions via *Add child
   permission*). Confirm the relationship names offered match the file; if not, update the file and re-run `npm test`.
   Page `/support/` with page permission *Customer contacts* only.
9. **Site settings** from `portal/site-settings.json` (Power Pages Management → Site Settings).
10. **Web file and template**: upload `portal/web-files/support-requests.js` as web file `/support-requests.js`
    (partial URL `support-requests.js`, parent page Home); create web template *Support requests* from
    `portal/web-templates/my-requests.html` and a page template using it for `/support/`. Add a page
    `/support/request/` with a **form** on *Support request*, mode **Updates an existing record** (record ID from the
    `id` query string), so the documents subgrid can upload.
11. **Dry run** with all four people in separate InPrivate windows, then delete the requests the dry run created
    (keep Alex's and Taylor's seed requests).

## Screens to capture (1920×1080, browser zoom 100 %, light theme)

| Scene id | File | What must be on screen |
|---|---|---|
| `signup-screen` | `screens/external-id-signup.jpg` | InPrivate window: portal → Sign in → *Contoso customers*; the external tenant's sign-up page (e-mail, code, password, name) as Riley; then the portal home signed in as Riley Demo with the Support menu item. |
| `requests-screen` | `screens/support-requests.jpg` | `/support/` as Riley: Alex's Northwind request listed, Taylor's (Adventure Works) **not**; Riley submits "Pallet arrived damaged" (Delivery); "Request sent", new row on top with its SR reference. |
| `documents-screen` | `screens/request-documents.jpg` | The request page with the documents subgrid; Riley adds `pallet-photos.pdf`. Second capture: SharePoint *Customer docs* → the Support request library → folder for that request with the PDF. |
| `isolation-screen` | `screens/isolation.jpg` | (a) Taylor on `/support/`: only Adventure Works rows. (b) Jordan (signed up, no registered contact): access denied on `/support/`. (c) Riley, DevTools console: run `ContosoSupport.createClient({fetch: fetch.bind(window), getToken: () => ContosoSupport.tokenFromShell(shell)}).createRequest({title: 'Forged request', category: 100000003}, '<Alex contact ID>')` and show the rejected promise (HTTP status + message). **If the forged create succeeds, stop:** that's a finding — record it in README, delete the row, and re-record this scene without (c). |

## Masking

Run `pipeline/mask.js` before capturing. Mask: the workforce and external tenant domains (keep `riley.demo` etc.
readable), the portal URL host, the external tenant ID, app/client IDs, contact and record GUIDs (including Alex's
contact ID in the console capture), the verification code e-mail contents except the subject.

## Tear-down

1. Power Platform admin center → Power Pages → delete the **Contoso support** site; delete solution `Customer portal`
   (table, form) and the seed accounts/contacts in `DEV`; turn off the server-based SharePoint integration if it was
   off before.
2. SharePoint: delete *Customer docs*, then remove it from the deleted sites in the SharePoint admin center.
3. External tenant (Learn's prerequisites for deletion): delete every user except the admin (Riley, Alex, Taylor,
   Jordan), delete the user flow, delete **all** app registrations including `b2c-extensions-app`, then Entra admin
   center → Manage tenants → select *Contoso customers* → **Delete**. Then
   `az group delete -n rg-mglab-deep-dive-06 --yes` once the tenant resource is gone.
4. If Lab Admin started a Power Apps Premium trial for this demo, nothing to undo (it expires); note it in the lab log.
