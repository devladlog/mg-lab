# Demo shot list — DEVLADLOG Deep Dive #11, Multi-tenant SaaS on Azure

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription** for everything on screen. Offline (container, no Azure): 57 xUnit tests and
11 Pester tests pass, `bicep build` and `bicep lint` are clean, the SQL scripts parse with Microsoft's T-SQL parser.
**Not yet run against Azure / SQL Server:** the Bicep deployment, the SQL scripts, the Graph calls, consent in a second
tenant. Record the outcome of each in the README ("Not verified in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host): Windows Terminal with PowerShell 7 for the calls, **SSMS** for SQL, Edge for the
Entra admin center and the Azure portal. No Hyper-V VM is needed. (Optional dry run of `sql/001`, `002` and
`verify-rls.sql` on **CON-SQL01**, SQL Server 2022 Developer at 10.50.0.30, in a scratch database `tenants_scratch`:
row-level security is the same feature. `003-grant-app.sql` does not run there: `FROM EXTERNAL PROVIDER` is Azure SQL only.)

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-11`, West Europe)

| Resource | SKU | Estimated cost |
|---|---|---|
| App Service plan (Linux) | **F1 Free** | €0 (shared compute, daily CPU quota) |
| Web app `app-saas-<suffix>`, .NET 10, system-assigned identity | on the F1 plan | €0 |
| Azure SQL logical server `sql-saas-<suffix>`, Microsoft Entra-only | no charge for the server | €0 |
| Azure SQL database `tenants` | **General Purpose serverless Gen5 2 vCores, free offer** (`useFreeLimit`, `AutoPause`) | €0 within the monthly allowance (Learn: free tier); pauses instead of billing. Max 10 free databases per subscription: check none is left from episode 3 (its resource group should be deleted). |

No Application Insights, no Key Vault, no storage. Total for one recording: about €0. Check the
[pricing page](https://azure.microsoft.com/pricing/details/azure-sql-database/single/) on the day; delete the group right after.
The budget alert `mglab-monthly` (€30) stays active.

**Microsoft Entra**
- **Provider tenant = the lab tenant.** Users (lab, fictional): `labadmin` (recording account; will hold `Platform.Admin`),
  `alex.demo` and `sam.demo` (users of customer **Adventure Works**; the lab tenant is onboarded as that customer).
  No licences are needed beyond what they have.
- **A second tenant for customer Northwind Traders** (a multitenant demo needs a real second tenant): Entra admin center >
  Manage tenants > Create > Microsoft Entra ID (workforce), name "Northwind Lab", domain `northwindlab<suffix>.onmicrosoft.com`.
  Created by the owner **once, before recording**, using a throwaway sign-in; it has one member user **`riley.demo`** created
  in that tenant by its administrator. Free; deleted in tear-down. The tenant's real domain and ID are masked on screen.
- Two app registrations in the provider tenant, created by `scripts/New-SaasApps.ps1`: `contoso-saas-api`, `contoso-saas-cli`.

**Local tools on the laptop:** Azure CLI, .NET SDK 10, Bicep CLI, PowerShell 7.4+, SSMS, the repo checked out.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/11-multi-tenant-saas-on-azure
   dotnet test tests/TenantApi.Tests -m:1                          # expect Passed: 57
   pwsh -NoProfile -c 'Invoke-Pester ./tests'                      # expect Tests Passed: 11
   bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
   ```
2. **Optional dry run of the SQL** on CON-SQL01 (SSMS, `tenants_scratch`): run `001-schema.sql`, `002-rls.sql`, then
   `verify-rls.sql`; expect 2 / 1 / 0 and error 33504. Drop the scratch database afterwards.
3. **App registrations** (as `labadmin`, provider tenant)
   ```powershell
   az login                                              # off camera
   ./scripts/New-SaasApps.ps1 -WhatIf
   $ids = ./scripts/New-SaasApps.ps1                     # prints ApiClientId and CliClientId
   az ad sp create --id $ids.ApiClientId; az ad sp create --id $ids.CliClientId   # service principals in the provider tenant
   ```
   Portal: Enterprise applications > `contoso-saas-api` > Users and groups > assign **`labadmin` → Platform administrator**.
   Enterprise applications > `contoso-saas-cli` > Permissions > **Grant admin consent** for the lab tenant (this is
   Adventure Works' consent). **Check and write into the README:** that `api://<appId>` was accepted as the Application ID URI
   of a multitenant app (if not, set `https://<verified domain>/saas` in the app's Expose an API blade and in the script).
4. **Customer consent in the second tenant** (as that tenant's administrator, in a private browser window):
   ```powershell
   Import-Module ./scripts/SaasLab.psm1 -Force
   Get-AdminConsentUrl -CustomerTenantId <northwind tenant id> -CliClientId $ids.CliClientId -ApiClientId $ids.ApiClientId
   ```
   Open the URL, sign in as the Northwind administrator, accept. The redirect lands on the native-client page: that is
   expected, nothing needs to listen. Check: Entra admin center (Northwind tenant) > Enterprise applications shows both apps.
5. **Azure**
   ```bash
   az group create -n rg-mglab-deep-dive-11 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-11 -f infra/main.bicep -p infra/main.bicepparam \
      -p apiClientId=<ApiClientId> homeTenantId=<lab tenant id> sqlAdminLogin=<labadmin UPN> \
         sqlAdminObjectId=$(az ad signed-in-user show --query id -o tsv) \
      --query properties.outputs -o json > /tmp/saas-outputs.json       # don't show on camera
   az sql server firewall-rule create -g rg-mglab-deep-dive-11 -s <sql server name> -n laptop --start-ip-address <laptop ip> --end-ip-address <laptop ip>
   ```
   **Check on first deploy and write the result into the README:** (a) F1 accepts `DOTNETCORE|10.0`; (b) the free database
   was created (portal > database > Overview shows the free offer banner); (c) the deployment time.
6. **SQL** (SSMS, Microsoft Entra MFA as labadmin, database `tenants`): run `001-schema.sql`, `002-rls.sql`; for
   `003-grant-app.sql` enable SQLCMD mode and put `:setvar AppIdentity "<web app name>"` on top (the system-assigned
   identity has the web app's name). Run `verify-rls.sql` once: expect **2 / 1 / 0** and **error 33504**. It rolls back.
7. **Publish the app**
   ```bash
   dotnet publish src/TenantApi -c Release -o publish && (cd publish && zip -qr ../app.zip .)
   az webapp deploy -g rg-mglab-deep-dive-11 -n <web app name> --src-path app.zip --type zip
   curl https://<web app host>/healthz        # expect Healthy
   ```
   If the first call to `/me` is 500, check that the managed identity user exists (step 6) and that the app settings
   `Entra__ClientId` and `Entra__HomeTenantId` are present (portal > web app > Environment variables).
8. **Onboard Adventure Works only** (as `labadmin`, the only Platform.Admin). Northwind is onboarded on camera, in the `isolation-screen` take:
   ```powershell
   $admin = Get-DeviceCodeToken -TenantId <lab tenant id> -ClientId $ids.CliClientId -Scope "api://$($ids.ApiClientId)/Requests.ReadWrite" -Label 'labadmin'
   Invoke-SaasApi -BaseUrl $url -Token $admin -Method PUT -Path "/admin/tenants/<lab tenant id>"       -Body @{ name = 'Adventure Works'; plan = 'starter' }
   ```
   **Check:** the `labadmin` token contains `roles: ["Platform.Admin"]` (`Get-TokenClaims $admin`). If `roles` is missing, the
   role assignment in step 3 did not take effect: sign in again in a fresh session. Expect 201.
9. **Dry run** the whole sequence once. Rate-limit takes need a quiet minute beforehand (fixed one-minute window). Then
   delete all rows to restart from zero: as the SQL admin run
   `EXEC sys.sp_set_session_context N'TenantId', '<id>'; DELETE dbo.PurchaseRequests;` for each tenant (the policy
   also applies to the delete).

## Screens to capture (1920×1080, terminal font 18 pt, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `tokens-screen` | `screens/tokens.jpg` | Terminal: `$aw = Get-DeviceCodeToken …` (alex.demo, lab tenant) and `$nw = Get-DeviceCodeToken …` (riley.demo, Northwind Lab); then `Get-TokenClaims $aw \| select tid, iss, scp, ver` and the same for `$nw`: two different `tid` values and matching `iss`. **Mask** the middle of both tenant ids (`pipeline/mask.js` or blur in editing). The device-code prompt (code and URL) may be shown; never the tokens. |
| `isolation-screen` | `screens/isolation.jpg` | Terminal, `Invoke-SaasApi` one call per line with the status visible: Northwind POST ×2, Adventure Works POST ×1; GET /requests for each (2 rows vs 1 row); Adventure Works GET of a Northwind id → 404; Adventure Works GET /requests with `-Headers @{'X-Tenant-Id'='<northwind id>'}` → still 1 row; FIRST (before any Northwind row exists) Northwind GET /me → 401 (valid token, tenant not onboarded), then `labadmin` PUT `/admin/tenants/<northwind id>` `@{ name = 'Northwind Traders'; plan = 'business' }` → 201 and the same GET /me now → 200 (this is the order to record: 401, onboard, 200, then the POSTs); at the end PUT the same tenant with `status = 'suspended'` then Northwind GET /requests → 403; PUT back to `active`. Web app host masked. |
| `rls-screen` | `screens/rls.jpg` | SSMS, connected as labadmin to `tenants`: `SELECT COUNT(*) FROM dbo.PurchaseRequests` → 0; `EXEC sys.sp_set_session_context N'TenantId', '<northwind id>'; SELECT Title, TenantId FROM dbo.PurchaseRequests;` → 2 rows; same with Adventure Works → 1 row; then the result sets of `verify-rls.sql` (A 2, B 1, none 0, error 33504). Server name and tenant ids masked. |
| `limits-screen` | `screens/limits.jpg` | Terminal as Adventure Works (starter): `1..26 \| % { Invoke-SaasApi … POST /requests }` showing 201 ×25 then 409 with "Plan limit reached" (delete the rows first, step 9); then `1..35 \| % { Invoke-SaasApi … GET /me }` alternating `$alex` and `$sam` tokens: 200 until about 30, then 429; immediately Northwind GET /me → 200. (If the 26-POST loop is slow, the one-minute window can reset; run it fast.) |

Reset before each full take: PUT Northwind to `suspended` is not enough, delete the Northwind catalog row
(`DELETE dbo.Tenants WHERE TenantId = '<northwind id>'` after its rows are deleted) so that the 401 shows again; the app caches
catalog lookups for 30 s, so wait half a minute or restart the web app.

Capture order: tokens → isolation → rls (the rows exist from isolation) → limits (clear rows first).

## Masking notes
Tenant ids and domains (both tenants), the web app and SQL server names, the subscription id, the client ids if they show
tenant-identifying names, user principal names other than `*.demo`. Never show access tokens, device codes after use, or
the SQL admin's sign-in prompt.

## Tear-down
1. `az group delete -n rg-mglab-deep-dive-11 --yes --no-wait` (removes web app, plan, SQL server, database).
2. The laptop firewall rule goes with the group; nothing else to clean in Azure.
3. Provider tenant: delete the app registrations `contoso-saas-api` and `contoso-saas-cli` (Entra admin center > App
   registrations > Delete; then Deleted applications > permanently delete) and remove the `labadmin` role assignment.
4. Second tenant "Northwind Lab": delete `riley.demo` and the enterprise apps, then Manage tenants > Delete (needs the
   tenant's prerequisites: no users except you, no apps, no subscriptions). If you keep it for later episodes, at least remove
   the consent (Enterprise applications > both apps > Delete).
5. SSMS: remove saved connection entries; CON-SQL01: drop `tenants_scratch` if used.
