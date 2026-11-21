# Demo shot list — DEVLADLOG .NET #2 ASP.NET Core Web APIs

Code and tests were built and run in the container (`dotnet test`: 28 passed; `deploy/local-demo.sh` run against
the local API, output in [`deploy/local-demo.output.txt`](deploy/local-demo.output.txt)).
**Needs tenant:** `entra-app`, `entra-token`, `entra-selfapprove` (Microsoft Entra ID + Azure subscription).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET SDK 10.0.1xx | includes `dotnet user-jwts` | free |
| Lab Microsoft Entra tenant, rights to create app registrations and assign app roles | use a lab admin account | free |
| Test user **Sam Approver** in the lab tenant | gets the `Claims.Approve` app role; the Azure CLI signs in as Sam for the Azure screens | free |
| Azure subscription (lab) with the €10 budget alert | App Service plan **Free F1, Linux** | €0 |
| Azure CLI, `jq`, `zip`, `curl` | `call-api.sh` uses `jq` to show token claims | free |
| Masking | `pipeline/mask.js` in the portal; blur every GUID (tenant, client ID, oid) and the app host name | — |

## Setup

### Local (screen 1)
```bash
cd series/net/episodes/02-asp-net-core-web-apis
dotnet test -m:1                                                  # expect Passed: 28
dotnet user-jwts create --project src/ExpenseClaims.Api           # BEFORE dotnet run on a fresh machine (signing key)
dotnet run --project src/ExpenseClaims.Api --launch-profile http  # http://localhost:5252, leave running
```

### Microsoft Entra ID (before screen 2) — needs tenant
1. **Entra admin center → App registrations → New registration**: name `contoso-expense-claims-api`,
   *Accounts in this organizational directory only*, no redirect URI → **Register**. Note the client ID and tenant ID.
2. **Expose an API** → *Add* Application ID URI (accept `api://<client-id>`) → **Add a scope**: `Claims.Submit`,
   *Admins and users*, display names "Submit and read expense claims" → **Add scope**.
3. Same page → **Authorized client applications → Add a client application** → client ID
   `04b07795-8ddb-461a-bbee-02f9e1bf7b46` (Azure CLI), tick `Claims.Submit` → **Add application**.
   (Without this, `az account get-access-token` fails with AADSTS65001.)
4. **App roles → Create app role**: display name `Claims approver`, allowed member types *Users/Groups*,
   value `Claims.Approve`, enabled → **Apply**.
5. **Enterprise applications → contoso-expense-claims-api → Users and groups → Add user/group** → Sam Approver →
   role *Claims approver* → **Assign**.

### Azure (before screen 3) — needs tenant
```bash
az login                      # as Sam Approver; not on camera
az account set --subscription <lab subscription>
APP=contoso-claims-<4 digits> TENANT_ID=<tenant-id> API_CLIENT_ID=<client-id> ./deploy/deploy-appservice.sh
```
Expect `==> https://<host>/healthz` and `Healthy` at the end (2–4 min).

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/local-demo.jpg`** — *Local tokens with dotnet user-jwts* (no tenant)
   - Second terminal, dark theme, font ≥ 18 pt: `./deploy/local-demo.sh`
   - In frame: step 1 `HTTP/1.1 401` + `WWW-Authenticate: Bearer`; step 4 403 Forbidden; step 6 409
     "Claim already approved."; step 7 `201 201 201 429 429`. Tokens print truncated; nothing to mask.
   - Restart `dotnet run` before a retake (the in-memory store and the rate-limit window persist while it runs).

2. **`screens/entra-app.jpg`** — *The API in Microsoft Entra ID* (**needs tenant**)
   - App registration → **App roles** (Claims.Approve, Users/Groups, Enabled) and **Expose an API** (scope
     `Claims.Submit`, Azure CLI under Authorized client applications). Two crops are fine.
   - **Mask** client ID, tenant ID, Application ID URI GUID, any admin names.

3. **`screens/entra-token.jpg`** — *A real Entra token, accepted* (**needs tenant**)
   - `./deploy/call-api.sh https://<host> <client-id>`
   - In frame: jq summary with `aud` = `api://…`, `iss` = `https://sts.windows.net/…/`, `ver` = `1.0`,
     `scp` = `Claims.Submit`, `roles` = `["Claims.Approve"]`; then the POST `<- HTTP 201`. Note the new claim `id`.
   - **Mask** every GUID (aud, iss, `submittedBy`) and the host name.
   - If `ver` shows `2.0`, the app registration was set to v2 tokens: change the authority setting to
     `https://login.microsoftonline.com/<tenant>/v2.0` and the audience to `<client-id>`, or reset
     `requestedAccessTokenVersion` to null — and fix the narration.

4. **`screens/entra-selfapprove.jpg`** — *The rule holds with real identities* (**needs tenant**)
   - `./deploy/call-api.sh https://<host> <client-id> <id from screen 3>` → the approve call shows `<- HTTP 409`
     and "You can't approve your own claim." (Sam submitted it, Sam tries to approve it).
   - **Mask** GUIDs and host.

## Tear-down
```bash
az group delete --name rg-mglab-net02 --yes --no-wait
dotnet user-jwts clear --project src/ExpenseClaims.Api --force
rm -rf deploy/out
```
In Entra: delete the app registration `contoso-expense-claims-api`, and the enterprise application of the same name
if it is still listed. Confirm the resource group is gone in the portal.
