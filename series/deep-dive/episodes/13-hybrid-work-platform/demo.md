# Demo shot list — DEVLADLOG Deep Dive #13, Hybrid Work Platform

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription** for everything on screen. Offline (container, no Azure): 41 API tests (incl. Azurite), 7 page tests and
25 Pester tests pass, `bicep build` and `bicep lint` are clean, the deployment zip builds and every function module loads.
**Not yet run against Azure / Teams:** the Bicep deployment, the ACS token call, the Graph call, the join itself, the Teams tenant settings.
Record the outcome of each check in the README ("Not verified in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host). **No Hyper-V VM is needed** and no Windows Server role is involved.
- **Windows Terminal, PowerShell 7.4+**, with modules `Microsoft.Graph.Authentication` and `MicrosoftTeams` (`Install-Module`, CurrentUser scope).
- **Microsoft Edge**, two windows: a normal profile signed in as `labadmin` (Teams on the web, Azure portal, Teams admin center) and an **InPrivate** window for the guest
  (no sign-in, microphone allowed for the site). Use a headset or the laptop microphone; record the guest audio.
- **Azure CLI**, **Bicep CLI**, **Node.js 22 or later** (the zip is built locally; the function runs on Node 24), the repo checked out.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-13`, West Europe; check Flex Consumption first:
`az functionapp list-flexconsumption-locations -o table`)

| Resource | SKU | Estimated cost for a recording day |
|---|---|---|
| Function app `func-hyb-<token>` on a Flex Consumption plan | **FC1**, Node.js 24, 2,048 MB instances, max 10 instances, no always-ready instances | billed per execution and GB-second: a few dozen calls, cents |
| Storage account `sthyb<token>` | Standard_LRS, shared keys off (code package, host state, `invites` table) | cents |
| Azure Communication Services `acs-hyb-<token>` | resource itself has no fixed fee; data location Europe; local (key) auth off | usage only: one guest, a few minutes of audio, billed per participant-minute. **Look up the price on the [ACS pricing page](https://azure.microsoft.com/pricing/details/communication-services/) on the day and write it into the README** (not verified: the page did not show a number when this was prepared). The Teams side is covered by the Teams licence (Learn) |
| User-assigned managed identity `id-hyb-<token>` | — | free |
| Log Analytics + Application Insights | PerGB2018, 30-day retention | a few MB: cents |

Total: **well under €1** if the group is deleted the same day. Budget `mglab-monthly` (€30) is not at risk.

**Microsoft 365 lab tenant**
- **Licences:** Microsoft 365 E5 trial (Teams, Exchange). `labadmin` is the **host** and a Teams administrator. **No other licence is needed**, and **the guest has no account at all**:
  the guest types a display name ("Riley Guest"). Do not use the `riley.demo` account as the guest (it would not be an external user).
- **Teams settings** (changed only if the readiness check fails, and reverted in tear-down): `AllowAnonymousUsersToJoinMeeting` on the policy that applies to `labadmin`
  (default True), `DisableAnonymousJoin` False, `AutoAdmittedUsers` not `Everyone`. Policy changes can take up to 24 hours (Learn): check the day before.
- No app registration is needed: Graph is called with the delegated scope `OnlineMeetings.ReadWrite` consented by `labadmin` at sign-in.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/13-hybrid-work-platform
   (cd src/api && npm ci --no-audit --no-fund && npm test)       # expect: tests 41, pass 41
   (cd src/join && npm ci --no-audit --no-fund && npm test)      # expect: tests 7, pass 7, bundle ok
   pwsh -NoProfile -c 'Invoke-Pester ./tests'                    # expect: Tests Passed: 25
   bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
   ```
2. **Teams readiness** (the day before, off camera)
   ```powershell
   Connect-MicrosoftTeams                                         # as labadmin
   ./scripts/Test-GuestJoinReadiness.ps1                          # expect three rows Passed
   ```
   If a row fails, fix it with the Learn commands (`Set-CsTeamsMeetingConfiguration -DisableAnonymousJoin $false`, `Set-CsTeamsMeetingPolicy -Identity Global -AllowAnonymousUsersToJoinMeeting $true`,
   `-AutoAdmittedUsers EveryoneInCompany`), write the previous values in the README, and wait for propagation.
3. **Azure**
   ```bash
   az login                                                       # off camera
   az group create -n rg-mglab-deep-dive-13 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-13 -f infra/main.bicep -p infra/main.bicepparam \
      --query properties.outputs -o json > /tmp/hybrid-outputs.json                 # don't show on camera
   ```
   **Check on first deploy and write the result into the README:** (a) Flex accepted `node` 24, (b) the deployment time, (c) the ACS resource shows "Local authentication: Disabled".
4. **Package and deploy**
   ```powershell
   ./scripts/Build-Package.ps1 -OutFile ./hybrid-api.zip          # expect: Wrote ... (about 13.6 MB)
   az functionapp deployment source config-zip -g rg-mglab-deep-dive-13 -n <functionAppName> --src ./hybrid-api.zip
   ```
   Check `https://<functionAppName>.azurewebsites.net/api/join` shows the page with "This page needs an invitation link from your host."
   **Check and write into the README:** that `POST /api/token` with a made-up code returns 403 (not 500): a 500 means the function cannot reach the table or ACS
   (look in Log stream: role assignments can take a few minutes to propagate; if `createUserAndToken` returns 403, the role is not enough: assign *Contributor* on the ACS resource and record it).
5. **Function key** (never on camera): 
   ```powershell
   $key = (az functionapp keys list -g rg-mglab-deep-dive-13 -n <functionAppName> --query functionKeys.default -o tsv) | ConvertTo-SecureString -AsPlainText -Force
   ```
6. **Graph sign-in** as `labadmin`: `Connect-MgGraph -Scopes OnlineMeetings.ReadWrite` (consent once).

## Screens to capture

Capture at 1920x1080, mask what is listed, save as `screens/<name>.jpg` (names match `script.yaml`).

| Screen | What must be on it | Masking |
|---|---|---|
| `meeting.jpg` | Windows Terminal. `./scripts/Invoke-HybridInvite.ps1 -ApiBaseUrl https://<functionAppName>.azurewebsites.net -FunctionKey $key -Subject "Partner sync" -WhatIf` (prints the `POST /me/onlineMeetings` operation), then the same without `-WhatIf`: subject, `LobbyScope organizer`, `HostJoin`, `GuestLink` (`.../join#i=...`), `ExpiresOn`, `MaxUses 3` | function host name; tenant id and meeting id inside the Teams link; all but the first 4 characters of the invite code. The function key never appears |
| `lobby.jpg` | Split screen. Left: Edge InPrivate on the guest link, name "Riley Guest", **Join**, page text "Waiting in the lobby. The host will let you in." Right: Teams on the web as `labadmin`, joined to the same meeting (the guest cannot enter before a Teams user is present), lobby notification "Riley Guest". Do not admit yet | tenant name and Teams meeting id in the address bar |
| `connected.jpg` | After **Admit**: guest page "You are in the meeting." with Mute enabled; Teams participants list showing the guest labelled external. The guest unmutes and speaks one sentence; then **Leave** and the participant disappears | as above |
| `readiness.jpg` | Windows Terminal: `./scripts/Test-GuestJoinReadiness.ps1` with three `Passed` rows; then Teams admin center > Meetings > Meeting policies > Global > *Meeting join & lobby* showing the same settings | tenant name |

Optional extra take (not in the script, good for the README and a Short): an invitation created with `-MaxUses 1` opened twice shows "This invitation is no longer valid. Ask your host for a new one." the second time,
and Application Insights / Log stream shows `invite refused: exhausted`.

## Tear-down

```powershell
az group delete -n rg-mglab-deep-dive-13 --yes --no-wait          # function, storage, ACS (this revokes every issued token), identity, insights
Remove-Item ./hybrid-api.zip, /tmp/hybrid-outputs.json -ErrorAction SilentlyContinue
Disconnect-MgGraph; Disconnect-MicrosoftTeams
```
- Revert any Teams setting changed in step 2 to the value written in the README.
- The Graph meeting expires on its own (60 days after start, Learn); delete it from the Teams calendar if one was created through the UI.
- Close the InPrivate window (it clears the page and the microphone permission).
- Check the resource group is gone: `az group exists -n rg-mglab-deep-dive-13` returns `false`; delete `screens/` captures that were not masked.
