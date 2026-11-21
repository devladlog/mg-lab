# DEVLADLOG Deep Dive #13 — Hybrid Work Platform (Teams meetings + guest join with Azure Communication Services)

Contoso is half in the office, half remote, and its partners have neither a Teams licence nor an account. The episode builds
one thing end to end: a **host creates a Teams meeting with Microsoft Graph**, a small **broker** (Azure Function) turns the
meeting link into a **one-time guest invitation**, and the guest joins the *real* Teams meeting from a Contoso web page through
the **Azure Communication Services (ACS) Calling SDK**, waiting in the Teams lobby until the host admits them.

```
Host (labadmin)                 Broker: Azure Function (Flex Consumption, Node.js 24, managed identity)        Guest browser
 New-HybridMeeting ──Graph──►   POST /api/invites  (function key = the HOST)                                    page /join#i=<code>
 POST /me/onlineMeetings         validate Teams link · store SHA-256(code), expiry, max uses  ► Table Storage   POST /api/token {code, name}
  lobby: organizer only          POST /api/token   (anonymous = the GUEST)                                       ◄ ACS token (voip, 60 min) + meeting link
 invite URL to the guest         count a use (ETag) · ACS createUserAndToken via Entra, no key ► ACS resource    callAgent.join({ meetingLink })
                                                                                                                 Teams: guest waits in the lobby, host admits
```

- **Scope, honestly.** The blog's Complete Guide bundles an SPFx web part, a Viva Connections card, Graph presence, Power Automate,
  Viva Insights (a placeholder there), governance scripts and a custom ACS calling portal. Viva, SharePoint and Power Automate are
  the subject of episodes 12 and 4, so this episode keeps only the part that is specific to hybrid *meetings*: guests in Teams meetings.
  The adoption and cost percentages in the guide have no source and are not repeated.
- **The ACS retirement.** Microsoft's retirement and breaking-changes guide says ACS Chat, SMS, Email, Advanced Messaging and Rooms
  are being retired and "will no longer be available after September 30, 2028"; the Calling SDK keeps working until then, and "to
  continue receiving support, you need to use ACS SDKs in conjunction with a Microsoft Teams-aligned product or service". That is
  why the custom (non-Teams) calling of the blog guide is **not** built: only Teams interoperability is.
- **No secrets.** The function reaches storage and ACS with one user-assigned managed identity; the ACS resource has
  `disableLocalAuth: true`; invite codes are stored only as SHA-256 hashes; the host's function key is read at run time and never
  written to a file.
- **A guest is not a user.** Each join gets a new ACS identity with the `voip` scope and a 60-minute token. The invite code is the only
  credential the guest holds, and it lives in the URL **fragment**, which a browser never sends to a server or in a `Referer` header.

| Path | What it is |
|---|---|
| [`contract/hybrid.json`](contract/hybrid.json) | Meeting defaults (lobby `organizer`, presenters `organizer`, chat `limited`), invite limits, token scope and lifetime, allowed meeting host, readiness rules. One source of truth: the PowerShell reads it, a test keeps the API's limits equal to it |
| [`src/api/src/lib/`](src/api/src/lib) | `meeting.ts` (Teams link + name validation), `invites.ts` (create/redeem, hash-only storage), `tableStore.ts` (Azure Table adapter with ETag retry), `memoryStore.ts` (test twin), `token.ts` (ACS identity + token), `handlers.ts` (HTTP logic), `config.ts`, `assets.ts`, `runtime.ts` |
| [`src/api/src/functions/`](src/api/src/functions) | Azure Functions v4 programming model: `POST /api/invites` (function key), `POST /api/token` (anonymous), `GET /api/join` and `/api/assets/{name}` (the page) |
| [`src/join/`](src/join) | The guest page: `state.ts` (pure: fragment parsing, call-state texts), `join.ts` (Calling SDK, audio only), `index.html`, `join.css`, `build.mjs` (esbuild into `src/api/site`) |
| [`scripts/HybridWork.psm1`](scripts/HybridWork.psm1) | `New-OnlineMeetingBody`, `New-HybridMeeting` (Graph `POST /me/onlineMeetings`), `New-GuestInvite`, `Test-GuestJoinReadiness` / `Get-GuestJoinReadiness` (Teams anonymous-join and lobby settings) |
| [`scripts/Invoke-HybridInvite.ps1`](scripts/Invoke-HybridInvite.ps1), [`Test-GuestJoinReadiness.ps1`](scripts/Test-GuestJoinReadiness.ps1), [`Build-Package.ps1`](scripts/Build-Package.ps1) | Demo driver (meeting + invite, `-WhatIf`), readiness report (exit code 1 on failure), builds and smoke-loads the deployment zip |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | ACS resource (`2025-09-01`, key auth off), storage (shared keys off) with the `invites` table, Flex Consumption **FC1** function app (Node 24), user-assigned identity with three role assignments, Application Insights |
| [`tests/HybridWork.Tests.ps1`](tests/HybridWork.Tests.ps1), [`src/api/test/`](src/api/test), [`src/join/test/`](src/join/test) | 25 Pester tests, 41 API tests (incl. Azurite), 7 page tests |
| [`demo.md`](demo.md), [`script.yaml`](script.yaml) | Shot list with the lab environment, and the draft video script |

## Test locally (no Azure, no tenant)

```bash
cd src/api  && npm ci --no-audit --no-fund && npm test      # tests 41, pass 41, fail 0 (about 20 s)
cd ../join  && npm ci --no-audit --no-fund && npm test      # tests 7, pass 7, "bundle ok: 6794 KB"
cd ../..    && pwsh -NoProfile -c 'Invoke-Pester ./tests'   # Tests Passed: 25, Failed: 0
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep      # no warnings
pwsh -NoProfile -File scripts/Build-Package.ps1 -OutFile /tmp/hybrid-api.zip          # Wrote ... (13.6 MB), every function module loads
rm -rf src/api/node_modules src/join/node_modules src/api/dist src/api/build-test src/join/build-test src/api/site
```

Versions used: Node 22.23 (the function targets Node 24, see gotchas), TypeScript 5.9, `@azure/functions` 4.17, `@azure/communication-identity` 2.0.0,
`@azure/data-tables` 13.3, `@azure/communication-calling` 2.0.0, esbuild 0.28, Azurite 3.38, Pester 6.2, PowerShell 7.6.

How the tests work:
- **API (41)**: invite creation and redemption (hash only, defaults, limits, expiry at the exact millisecond, malformed codes), the
  Teams link validator (accepts `/l/meetup-join/` and `/meet/` links; refuses `http`, lookalike hosts, `user@host` tricks, ports,
  personal Teams `teams.live.com`, other paths, over-long links), the HTTP handlers (uniform 403, no link or token in any error body, a bad
  name does not burn a use, an ACS failure after a counted use), a contract test (API limits equal `hybrid.json`, token lifetime in the SDK's 60–1440
  range, no key or connection string in the source, no identity read from headers), and the **Azurite** tests: `TableInviteStore` against
  Azurite, Microsoft's open-source storage emulator started as a child process (a devDependency; no Docker). The race test runs ten
  guests against a three-use invite: exactly three get in and seven are refused, through real `If-Match` / HTTP 412 handling.
- **Page (7)**: pure logic (the fragment parser, every SDK call state has a text, the lobby text and which buttons are enabled), and source checks (no
  query string, no key, the meeting link comes from the broker). `tsc` type-checks `join.ts` against the **real** `@azure/communication-calling` typings and esbuild
  bundles it.
- **Pester (25)**: the Graph body, `New-HybridMeeting` with `Invoke-MgGraphRequest` mocked (a stand-in function is defined for the mock because
  Microsoft.Graph is not installed here), `New-GuestInvite` with `Invoke-RestMethod` mocked (header, body, limits, no key in any output stream, `-WhatIf`),
  the readiness rules, and parse/secret checks over the scripts.

**What the tests cannot prove (needs the lab):** that Teams accepts the meeting body, that the ACS token really lets a browser join and that the lobby behaves as
described, that the role assigned in Bicep is enough to create identities, the Bicep deployment, Node 24 on Flex Consumption, the Teams tenant settings, and microphone/browser behaviour.
Everything on screen in the video comes from those lab runs (see `demo.md`).

## Deploy and run (needs the lab Azure subscription and tenant)

Runbook, costs, masking and tear-down are in [`demo.md`](demo.md). Short version:

```powershell
az group create -n rg-mglab-deep-dive-13 -l westeurope
az deployment group create -g rg-mglab-deep-dive-13 -f infra/main.bicep -p infra/main.bicepparam --query properties.outputs
./scripts/Build-Package.ps1 -OutFile ./hybrid-api.zip
az functionapp deployment source config-zip -g rg-mglab-deep-dive-13 -n <functionAppName> --src ./hybrid-api.zip
Connect-MgGraph -Scopes OnlineMeetings.ReadWrite
./scripts/Invoke-HybridInvite.ps1 -ApiBaseUrl https://<functionAppName>.azurewebsites.net -FunctionKey $key
```

## What we learned / gotchas

- **Calling is not going away, but custom calling is a dead end.** Per the retirement guide, calling scenarios keep working until
  30 September 2028 and support requires a Teams-aligned use; Chat, SMS, Email, Rooms and WhatsApp are being retired. The blog guide's
  portal that calls support agents by itself is therefore not rebuilt. The ACS UI library only gets "limited support ... as break-fix", so
  the page uses the Calling SDK directly: no React and no Fluent in the bundle.
- **A guest waits.** Learn (Join a Teams meeting): a Communication Services user is not admitted until at least one Teams user is in the
  meeting; then waits in the lobby until a Teams user admits them, unless "Who can bypass the lobby?" is set to Everyone. The page shows the `InLobby` state and enables only Leave.
- **The token default is 24 hours.** The Identity SDK typings say `tokenExpiresInMinutes` is "within [60,1440] ... If not provided, the default value of 1440 minutes (24 hours)". We ask for 60, the shortest allowed. Learn also warns that tokens dispensed freely and misused
  cost money, so the anonymous endpoint is gated by an invitation with an expiry and a use count, and `maximumInstanceCount` is capped at 10.
- **Anonymous join is two settings.** `Set-CsTeamsMeetingConfiguration -DisableAnonymousJoin` (tenant) and `Set-CsTeamsMeetingPolicy
  -AllowAnonymousUsersToJoinMeeting` (organizer's policy; default True). Learn also says the org-wide toggle "is going away" and recommends leaving it On and using the
  per-organizer policy, and that policy changes can take up to 24 hours. The education baseline sets the policy to FALSE for the Global policy, so a guest
  demo fails there. `Test-GuestJoinReadiness` reports both, and flags `AutoAdmittedUsers = Everyone` (guests would skip the lobby).
- **Delegated only.** Learn lists `OnlineMeetings.ReadWrite` (delegated) for `POST /me/onlineMeetings`; the application permission applies to `POST /users/{id}/onlineMeetings`
  and needs a tenant **application access policy**. The demo uses the delegated route as the host. The API also creates a standalone meeting that is not on the host's calendar.
- **Do not parse `joinWebUrl`.** Learn: "The format of the URL may change; therefore, users shouldn't rely on any information extracted from parsing the URL." The validator only checks https,
  the host `teams.microsoft.com` and the path prefix (`/l/meetup-join/` or `/meet/`). If Teams changes the format, invitations fail closed and the validator is the one place to change.
- **The invite goes in the fragment.** A query string reaches logs, proxies and `Referer` headers; a fragment does not leave the browser. The page also calls `history.replaceState` to drop it from the address bar.
- **Same refusal for everything.** Unknown, expired and used-up invitations all return 403 with one message, so the endpoint cannot be used to find valid codes. The reason is logged.
- **Optimistic concurrency for the use counter.** The table adapter reads the row, then updates with `If-Match` = the ETag it read; on 412 it re-reads. With ten parallel guests on a
  three-use invite each guest can lose at most three races, so five attempts are enough. Azurite proves the behaviour (the in-memory twin only proves the contract).
- **Strict mode and Graph.** `Invoke-MgGraphRequest` returns a Hashtable; under `Set-StrictMode` a missing `.subject` on a custom object throws, so the module indexes (`$r['subject']`) and the mocks return Hashtables. Hit in the first Pester run.
- **The Calling SDK bundle is large.** The minified bundle is 6.8 MB (the zip is 13.6 MB with dependencies). Its licence is Microsoft's SDK licence, not an open-source licence: read it before redistributing.
- **Learn names no minimum RBAC role for the Identity SDK.** The Entra quickstart assigns Contributor on the subscription to a dev service principal; the template assigns the built-in *Communication and Email Service Owner*
  (`c2f4ef07-c644-48eb-af81-4b1b4947fb11`, "access to all Communication and Email service operations") **scoped to the ACS resource only**. See "Not verified in the lab yet".
- **Chat and the meeting chat mode.** Learn: ACS users in a Teams meeting can chat through the Chat SDK, but the page is audio only; `allowMeetingChat` is `limited` (chat enabled during the meeting only).
- **Teams interop is not for Teams personal use**, and ACS joins to Teams meetings for personal use are unsupported (Learn). The validator refuses `teams.live.com`.

## Not verified in the lab yet

To be filled in during the recording, from the real runs: (1) that *Communication and Email Service Owner* on the ACS resource is enough for `createUserAndToken` (if the call returns 403, record it and
use Contributor on the resource); (2) that Flex Consumption accepts `node` 24 and the deployment zip; (3) that `disableLocalAuth: true` does not affect the Entra-authenticated identity calls; (4) the lobby scope that Teams
actually applies in this tenant (the module warns when it differs); (5) the exact wording of the Teams lobby and participant labels used in the video; (6) the deployment time and cost.

## References

- Retirement and breaking changes guide for ACS: https://learn.microsoft.com/azure/communication-services/acs-retirement-and-breaking-changes-guide
- Join a Teams meeting (BYOI, lobby behaviour): https://learn.microsoft.com/azure/communication-services/concepts/join-teams-meeting
- Teams external users overview (supported scenarios, pricing): https://learn.microsoft.com/azure/communication-services/concepts/interop/guest/overview
- Teams interoperability: https://learn.microsoft.com/azure/communication-services/concepts/teams-interop
- Join a Teams meeting with the Calling SDK (web): https://learn.microsoft.com/azure/communication-services/how-tos/calling-sdk/teams-interoperability
- Identity model (ephemeral identities, token handling): https://learn.microsoft.com/azure/communication-services/concepts/identity-model
- Authenticate to ACS (Entra ID, managed identity): https://learn.microsoft.com/azure/communication-services/concepts/authentication
- Authorize with Entra ID (Identity SDK sample): https://learn.microsoft.com/azure/communication-services/quickstarts/identity/service-principal
- Managed identity with ACS: https://learn.microsoft.com/azure/communication-services/how-tos/managed-identity
- Template reference `Microsoft.Communication/communicationServices` 2025-09-01: https://learn.microsoft.com/azure/templates/microsoft.communication/2025-09-01/communicationservices
- Graph: create onlineMeeting: https://learn.microsoft.com/graph/api/application-post-onlinemeetings ; onlineMeeting resource: https://learn.microsoft.com/graph/api/resources/onlinemeeting ; lobbyBypassSettings: https://learn.microsoft.com/graph/api/resources/lobbybypasssettings
- Teams anonymous participant access: https://learn.microsoft.com/microsoftteams/anonymous-users-in-meetings ; lobby: https://learn.microsoft.com/microsoftteams/who-can-bypass-meeting-lobby ; `Set-CsTeamsMeetingPolicy`: https://learn.microsoft.com/powershell/module/microsoftteams/set-csteamsmeetingpolicy
- Azure Functions Flex Consumption (Node.js 22/24 supported): https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan ; package deployment: https://learn.microsoft.com/azure/azure-functions/deployment-zip-push
- Blog Complete Guide: https://www.devladlog.com/articles/deep-dive/2025-09-08-hybrid-work-platform-teams-sharepoint-viva-azure-communication-services/
