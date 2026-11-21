# Demo shot list — Power BI #13 Embedded Analytics

## Lab environment

No VM and no Azure resource. Everything runs on the **Windows recording laptop** and in the **lab tenant** (`series/LAB.md`).
Episode 5 must be done: the model `ContosoSales` with the roles *Store Managers* and *Head Office*, the `UpnDomain` parameter set to the lab sign-in
domain, a refresh done, and the report with the page *Store security*, published to workspace **Contoso Sales (Lab)** on the Fabric trial capacity.

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Node.js 22 LTS (`node -v`), PowerShell 7, Windows Terminal, a browser (clean profile, no bookmarks bar) | free |
| PowerShell modules | `Microsoft.Graph` (`Install-Module Microsoft.Graph -Scope CurrentUser`) and `MicrosoftPowerBIMgmt` | free |
| Lab tenant: workspace | `Contoso Sales (Lab)` on the Fabric + Power BI 60-day trial capacity (West Europe), semantic model + report of episode 5 published | trial, €0 |
| Lab tenant: account | `labadmin` (Global Administrator, therefore also Fabric administrator, and workspace Admin) creates the app and sets the tenant settings | trial |
| Lab tenant: app users | none: the whole point is that `alex.demo` etc. never sign in. They are only names in the app's own table and UPNs in the identity | €0 |
| Entra app | `Contoso Embed (Lab)` + secret valid one month, group `Contoso Embed SPs (Lab)` | free |

Screens are recorded in the browser and Windows Terminal on the laptop. The app listens on `localhost` only.

## What was verified where

| Step | Verified in the container | Needs the lab tenant on the recording day |
|---|---|---|
| Server, identity limits, REST bodies, routes, refresh timing, static files | 22 `node:test` tests (fake `fetch`, real HTTP server), `npm start` smoke test: 200 for the page and the three scripts | the real calls to Entra ID and Power BI |
| `powerbi.min.js` globals (`window.powerbi`, `window["powerbi-client"]`, `TokenType.Embed`) | run in a Node `vm` | the page in a real browser |
| `New-EmbedServicePrincipal.ps1`, `Remove-...` | parsed by the PowerShell parser | **everything it does** (Graph + Power BI) |
| Tenant settings, effective identity with `USERPRINCIPALNAME()`, trial capacity | nothing | all of it, see "Write down" |

## Setup (off camera, once)

1. Episode 5 done (above). Note the **report id** and **workspace id** from the URL
   `https://app.powerbi.com/groups/<workspace>/reports/<report>/...`. Open the report in the service, make **Store security** the page it opens on (save).
   Check that the *Store Managers* role has the `Store Access` mapping and `UpnDomain` is the real sign-in domain: **View as > Other user** `alex.demo@<domain>` shows 1 store.
2. Copy `13-embedded-analytics` to `C:\MGLab\power-bi\ep13\` (no Windows user name in paths). In `src`: `npm ci --no-audit --no-fund`, `npm test` (expect 22 passed).
3. **Power BI admin portal > Tenant settings > Developer settings** (as `labadmin`): leave both settings OFF for now: the first screen shows them being turned on.
   Check **Integration settings** and **Developer settings** aren't blocked by a policy (write down anything unexpected).
4. Sign in to nothing in the app terminal yet. The service principal is created on camera (screen 1) or just before, see below.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `setup` | `screens/sp-setup.jpg` | (a) Terminal: `$sp = ./src/setup/New-EmbedServicePrincipal.ps1 -WorkspaceName 'Contoso Sales (Lab)'` (use `-WhatIf` first on camera, then for real; sign-in prompts for Graph and Power BI as `labadmin`, record the browser sign-ins off camera or cut them). Then, off camera: `$env:PBI_TENANT_ID = $sp.TenantId` etc. and `$env:PBI_CLIENT_SECRET = ConvertFrom-SecureString -AsPlainText $sp.ClientSecret` (never show it). (b) Entra admin center: **App registrations > Contoso Embed (Lab)**: Overview (blur IDs), **API permissions** empty, **Certificates & secrets** one secret. (c) Power BI admin portal, **Tenant settings > Developer settings**: turn on **Embed content in apps** and **Allow service principals to use Power BI APIs**, each *Specific security groups* = `Contoso Embed SPs (Lab)` > Apply. (d) Workspace **Manage access**: `Contoso Embed (Lab)` = **Member**. Compose these four as a quick montage. **Setting changes can take time to apply: if the next step fails with 401/403, wait a few minutes and retry (not verified in the docs: write down how long it took).** |
| `alex` | `screens/app-alex.jpg` | Terminal: set `$env:PBI_WORKSPACE_ID`, `$env:PBI_REPORT_ID`, `$env:PBI_UPN_DOMAIN` (off camera), `npm start`. Browser to `http://localhost:5173/`, user = Alex Demo. Expected: status line `loaded as alex.demo (roles: Store Managers), token expires ...`, page *Store security*: Visible stores **1**, Visible customers **247**, Sales amount **389,707.34**, table row Contoso Lisboa 389,707.34 / 483. Blur the **Who Am I** card (UPN with the domain). Check whether the free-trial banner appears (see "Write down") |
| `switch` | `screens/app-switch.jpg` | Same page, dropdown: **Riley Demo** (3 stores, 300 customers, **1,111,159.04**), **Jordan Demo** (5 stores, 301 customers, **1,862,401.98**), **Nobody Demo** (0 stores, blank sales, empty table). Values are `src/reference/expected/rls_matrix.csv` of episode 5. Write down what **Who Am I** shows for Alex: if it is the same UPN that was sent, the narration claim "the principal name from the token" is true; if not, adjust |
| `gotcha` | `screens/probe.jpg` | Second terminal with the same env variables: `node dist/server/probe.js`. Learn's expectation: a refusal (a service principal gets a failure when no username and role are sent). **Record the real status and error text.** If instead it prints "token issued WITHOUT an identity", rewrite the narration (it would mean the model has no role requiring one, or the behaviour changed) |

## Write down (the README's "Not verified" list)

1. Does the embedded report show a **Free trial version** banner on the trial capacity? Does `Generate Token` accept a service principal for a workspace on the Fabric trial capacity at all?
2. What does `USERPRINCIPALNAME()` return for the effective identity: exactly the `username` we send (`Who Am I`)?
3. Does the probe fail, and with what HTTP status and error code?
4. Does the token refresh work? Start the app with `$env:EMBED_LIFETIME_MINUTES = '6'` (refresh after about one minute, because the page refreshes five minutes before expiry), wait, and check the status line says `token refreshed for alex.demo` and the report stays on screen. (Record only the status line, not a six minute wait: cut.)
5. After changing Sam Demo in the service from Viewer to Contributor nothing changes in the app (roles in the service don't matter with an embed token): optional extra take.

## Masking

Blur: application (client) ID, tenant ID, the UPN domain (Who Am I, any `@domain`), workspace and report IDs in URLs and terminal, the secret (never on screen). The address bar shows only `localhost`.
`pipeline/mask.js` in the browser for the admin portal and Entra pages.

## Tear-down

1. Stop the app (Ctrl+C), close the terminals, `Remove-Item Env:PBI_*`.
2. `./src/setup/Remove-EmbedServicePrincipal.ps1` (removes the app, its secret and the group; the workspace role goes with the service principal).
3. Power BI admin portal: turn the two Developer settings off again (they were off before).
4. Delete `src\node_modules` and `src\dist` from `C:\MGLab\power-bi\ep13` if disk is tight.
5. Keep workspace `Contoso Sales (Lab)` and the episode 5 model: episodes 14 and later reuse them.
