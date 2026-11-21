# DEVLADLOG Power BI #13: Embedded Analytics

Same **Contoso Bikes** model as episodes 1-12, and the row-level security of **episode 5** (`Store Managers` reads the
hidden `Store Access` table with `USERPRINCIPALNAME()`, `Head Office` sees everything). Until now people opened the report in the
Power BI service. This episode puts the same report inside **an app of our own**, for people who have no Power BI licence and never sign in
to Power BI: **embed for your customers** (Learn: "app owns data").

Blog guide: <https://www.devladlog.com/articles/power-bi/2025-06-08-embedded-analytics-complete-guide-2025/>

What we build, in TypeScript on Node (no framework):

1. a **service principal** (Entra app + secret) that is a **Member** of the workspace, and the script that creates it
2. a small **back end** that gets an app-only Entra token (MSAL), reads the report (`Get Report In Group`) and asks for an
   **embed token** (`Generate Token`, V2) with an **effective identity**: the user's UPN and role come from the server, never from the browser
3. a **page** that embeds the report with `powerbi-client`, switches user, and replaces the token before it expires without reloading the report
4. a **probe** that sends the request without an identity, to show what Learn says happens

| Path | What it is |
|---|---|
| [`src/server/identity.ts`](src/server/identity.ts) | `buildIdentity`: username, roles, dataset, and the limits from Learn's `EffectiveIdentity` (256 chars, no spaces, 50 roles of at most 50 chars, no comma) |
| [`src/server/powerbi.ts`](src/server/powerbi.ts) | `PowerBiClient`: `getReport` and `generateEmbedToken` over an injected `fetch` |
| [`src/server/msal.ts`](src/server/msal.ts) | Service principal token with `@azure/msal-node`, scope `https://analysis.windows.net/powerbi/api/.default` |
| [`src/server/app.ts`](src/server/app.ts), [`main.ts`](src/server/main.ts) | `EmbedService` (alias to identity to token) and the HTTP server: `/api/users`, `/api/embed?user=`, four static files, GET only |
| [`src/server/lab-users.ts`](src/server/lab-users.ts) | The app's users and their roles (same as episode 5's `role_members.csv`; a test compares them) |
| [`src/server/config.ts`](src/server/config.ts) | Settings from environment variables, every problem reported at once, secret never printed |
| [`src/server/probe.ts`](src/server/probe.ts) | The gotcha: a token request without identity |
| [`src/client/embed.ts`](src/client/embed.ts), [`timing.ts`](src/client/timing.ts), [`src/public/index.html`](src/public/index.html) | The page: `powerbi.embed`, user switch, `setAccessToken` five minutes before expiry |
| [`src/setup/New-EmbedServicePrincipal.ps1`](src/setup/New-EmbedServicePrincipal.ps1), [`Remove-EmbedServicePrincipal.ps1`](src/setup/Remove-EmbedServicePrincipal.ps1) | Learn's steps 1, 2 and 4 (Microsoft Graph PowerShell + MicrosoftPowerBIMgmt), and the tear-down. `-WhatIf` supported |
| [`src/setup/lab.env.example`](src/setup/lab.env.example) | The six variables the app reads (zero GUIDs, no secret) |
| [`src/tests/`](src/tests) | `node:test`, 22 tests |
| [`tests/test_script.py`](tests/test_script.py) | pytest, 5 tests: `script.yaml` follows the brief (scenes, words, shorts, screens, outro) and every code scene is a real excerpt of `src/` |

## Run it

```bash
cd src
npm ci --no-audit --no-fund
npm test          # tsc, then node --test: 22 passed, 0 failed
# the real thing (needs the lab tenant, see demo.md): set the six PBI_* variables, then
npm start         # http://localhost:5173/
node dist/server/probe.js   # the gotcha
```

```bash
# from the episode folder (needs PyYAML)
python3 -m pytest tests -q   # 5 passed
```

Delete `src/node_modules` and `src/dist` afterwards (37 MB).

What the 22 tests cover: the identity limits; the REST requests against bodies shaped like Learn's samples (URL, method, bearer header,
`identities`, `lifetimeInMinutes`); the HTTP routes with a real server on an ephemeral port and a fake Power BI client (Alex gets
`Store Managers`, Jordan `Head Office`, extra query parameters like `roles=` are ignored, unknown users are 404, a Power BI error is a 502 with a
short message, the UPN domain is never in a response, only listed files are served); the refresh timing; configuration errors; and that the bundled
`powerbi.min.js` really defines `window.powerbi` and `window["powerbi-client"]` with `TokenType.Embed` and `Permissions.Read`
(it is run in a Node `vm`; the browser itself is not).

**Needs tenant** ([demo.md](demo.md)): everything that talks to Entra ID or Power BI: creating the service principal, the two tenant settings,
the token, the embedded report, the effective identity, the probe. The `.ps1` scripts were only parsed (PowerShell parser), never run.

## What we learned / gotchas

- **Two solutions, one decision.** Learn: *embed for your customers* (app owns data) authenticates with a service principal or a master user,
  the users don't need a Power BI licence; *embed for your organization* (user owns data) signs each user in with Entra ID and each needs a licence, and it
  **can't use a service principal**. A table in "What is Power BI embedded analytics?" also says R and Python visuals aren't supported in the first one.
- **Capacity.** Content must sit in a workspace on a Premium, Embedded or Fabric capacity. For development testing Learn allows free embed trial tokens
  (with Pro or PPU); in production a capacity is needed or the *Free trial version* banner stays. Fabric trial capacities are an F4 or F64 SKU.
  Whether the lab's trial capacity gives a clean embed is something the recording shows (see "Not verified").
- **Service principal setup is four things**, and two of them are not in code: the tenant settings **Embed content in apps** and **Allow service principals to use Power BI APIs**
  (both, for the security group), and the service principal as workspace **Member or Admin**. My Workspace isn't supported. Learn also says not to add API permissions to the app:
  they are never used and can cause errors that are hard to troubleshoot. Learn recommends a certificate over a secret for production; the lab uses a one month secret.
- **The server decides who the user is.** The browser sends an alias; the server looks up the roles in its own table and builds the identity. The test `the browser can't choose roles`
  sends `roles=Head Office` and checks it is ignored. An endpoint that takes a username and roles from the client would let anyone read any store.
- **Roles in the service don't count.** Learn: assigning users to roles in the service doesn't affect RLS when you use an embed token (app owns data); only the identity in the token does.
  And RLS normally doesn't apply to admins, members and contributors, but when you send an identity, that identity's RLS is applied.
- **No identity, no token (service principal).** Learn: with a service principal, token generation fails when you don't supply username and role; with a master user it succeeds and the data is
  **not filtered**. `probe.ts` shows the first case against the real service.
- **Identity details.** The username can be any ASCII string without spaces, up to 256 characters (cloud models), roles can't contain a comma and are at most 50 characters, up to 50 per identity.
  The caller must be a member or admin of both the dataset's and the report's workspace. `lifetimeInMinutes` can shorten the token's life, never extend it.
- **V2 workspaces, 50 items.** `Generate Token` needs V2 workspaces and takes at most 50 reports, 50 datasets and 50 target workspaces. For dashboards and tiles Learn points to the V1 calls.
- **Multi-tenant ISVs.** Learn recommends workspace-based isolation over RLS-only. Its service principal profiles article now says new multitenancy solutions should start with dedicated customer
  service principals. This episode is the single-tenant, RLS-based start of that road.
- **Token refresh.** The embed token expires; the page asks the server for a new one and calls `report.setAccessToken`, so the viewer doesn't lose their place. Learn's troubleshooting table lists `TokenExpired` (HTTP 403) for a token that was not replaced.

## Not verified

- Nothing was run against Entra ID or the Power BI service. REST bodies and URLs follow Learn's samples; the tests use a fake `fetch`.
- The page was never opened in a browser here; only the bundle's globals and the served files were checked.
- Whether `USERPRINCIPALNAME()` returns exactly the `username` of the effective identity (the demo checks it with the `Who Am I` measure of episode 5).
- Whether the trial capacity of the lab tenant shows the *Free trial version* banner, and whether a service principal can embed from it.
- `New-EmbedServicePrincipal.ps1` parses, but its Microsoft Graph and Power BI cmdlet calls were not run.

## References

- What is Power BI embedded analytics (comparison, capacities): <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embedded-analytics-power-bi>
- Embedded analytics access tokens: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-tokens>
- Embed with a service principal and a secret: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal> (certificate variant: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal-certificate>)
- Generate an embed token: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/generate-embed-token>; REST: [Generate Token](https://learn.microsoft.com/en-us/rest/api/power-bi/embed-token/generate-token), [Get Report In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/reports/get-report-in-group)
- Embed a report with RLS: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/cloud-rls>; security features: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embedded-row-level-security>
- Move to production (trial tokens, capacities): <https://learn.microsoft.com/en-us/power-bi/developer/embedded/move-to-production>
- Embed for your customers usage scenario: <https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-implementation-planning-usage-scenario-embed-for-your-customers>
- Service principal profiles and multitenancy: <https://learn.microsoft.com/en-us/power-bi/guidance/develop-scalable-multitenancy-apps-with-powerbi-embedding>
- JavaScript API: [handle events](https://learn.microsoft.com/en-us/javascript/api/overview/powerbi/handle-events), [override error messages](https://learn.microsoft.com/en-us/javascript/api/overview/powerbi/override-error-messages), [troubleshoot](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embedded-troubleshoot)
- Token with MSAL, scope `.default`: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal-certificate#step-5---authenticate-using-service-principal-and-a-certificate>
