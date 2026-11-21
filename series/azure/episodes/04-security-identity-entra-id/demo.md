# Demo shot list — DEVLADLOG Azure #4, An API with zero secrets

Everything below **needs the lab tenant** (Entra ID + Azure subscription), except the local checks. The episode
builder ran only local checks (20 xUnit, 21 pytest, Bicep lint/build with the Graph extension, a local API start).
No Entra objects or Azure resources were created.

## Prerequisites

| What | Notes |
|---|---|
| Lab tenant + Azure subscription with the €10 budget alert | A resource group you can create; Contributor on it (managed identity, container instance) |
| An account that can create app registrations and app role assignments | The Graph Bicep deployment runs as you: Learn lists `Application.ReadWrite.All` and `AppRoleAssignment.ReadWrite.All` (+ `Application.Read.All`) as the permissions per resource type. In the lab, use the Global Administrator account; pick a narrower role for real tenants after checking those pages |
| The fictional reader | Sign in as **Alex Demo** (a lab user) for `call-as-user.sh`, so the claims and portal show a fictional name. `deploy.sh` makes the signed-in user the reader and owner, so run it as Alex Demo, or pass Alex's object ID |
| Azure CLI ≥ 2.73 | Microsoft Graph Bicep needs it; `az bicep upgrade` so the Bicep CLI matches |
| .NET SDK 10, Python 3, curl | Run the API locally, show claims |
| Cost | Managed identity and Entra objects: no charge. One container instance (1 vCPU, 1 GB) for well under a minute per run: cents. Delete everything the same day |

## Setup (needs tenant)

```bash
cd series/azure/episodes/04-security-identity-entra-id
dotnet test tests/Contoso.Orders.Tests --artifacts-path /tmp/orders-artifacts   # 20 passed, before anything else
python3 -m pytest tests/python -q                                               # 21 passed
az login                                                     # as Alex Demo (or an admin, then pass Alex's object ID)
infra/deploy.sh rg-contoso-identity swedencentral            # what-if, then the deployment (~1-2 min)
infra/lab-preauthorize-cli.sh                                # LAB ONLY: lets `az` request Orders.Read without consent
```

If the deployment fails on `processorCanWrite` with a "principal not found"-type error right after the identity was
created, run `deploy.sh` again (directory replication); note it in the episode if it happens.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/graph-deploy.jpg` — scene `deploy` (needs tenant)
Terminal running `infra/deploy.sh rg-contoso-identity swedencentral`: the what-if lines for
`Microsoft.ManagedIdentity/userAssignedIdentities`, `Microsoft.Graph/applications`, `servicePrincipals`,
`appRoleAssignedTo` (×2), then the outputs table. If what-if can't show the Graph resources in detail, capture what
it shows and the deployment outputs; say so in the narration rather than claiming more.

### 2. `screens/app-roles.jpg` — scene `portal` (needs tenant)
Microsoft Entra admin center:
- App registrations → *contoso orders API* → **App roles**: `Orders.ReadWrite.All` (Applications), `Orders.Reader` (Users).
- Optionally **Expose an API**: App ID URI `api://<tenant>/contoso-orders`, scope `Orders.Read`, the Azure CLI as
  authorized client (after the lab script).
- Enterprise applications → *contoso orders API* → **Properties** (Assignment required = Yes) and **Users and
  groups** (Alex Demo → Orders.Reader; *id-contoso-order-processor* may only be listed via Graph — if it isn't shown
  in Users and groups, capture the managed identity's Enterprise application → **Permissions** blade instead).
- Also check **Certificates & secrets** shows none (good b-roll for "zero secrets").

### 3. `screens/call-as-user.jpg` — scene `user` (needs tenant)
Terminal 1: `infra/run-api-local.sh` (listening on http://localhost:5080). Terminal 2: `infra/call-as-user.sh`.
Expected: claims with `aud` = API client ID, `scp` = `Orders.Read`, `roles` = `["Orders.Reader"]`,
`kind` = delegated (user); `GET /orders -> 200`, `GET /me -> 200` (kind delegated), `POST /orders -> 403`.
If GET returns 401, check the API terminal: an audience error means the token is v1.0 (see the gotcha scene).

### 4. `screens/app-token.jpg` — scene `app` (needs tenant)
`infra/prove-app-token.sh rg-contoso-identity`. Expected log: `aud` = API client ID, `roles` =
`["Orders.ReadWrite.All"]`, `idtyp` = `app`, `kind` = app-only. The container is deleted at the end.
If the log says `python3: not found`, the azure-cli image changed: replace the image with a Python image
(e.g. a Microsoft-published Python base image) and keep the same `--command-line`; note it in README.

## Masking
- Tenant ID (`tid`, `iss`, App ID URI), object IDs (`oid`), client IDs, subscription ID, resource names with
  suffixes, the tenant name in the admin center header and the signed-in account (use Alex Demo).
- Never show a raw token: the scripts print claims only. Don't run `az account get-access-token` without `--query`
  on camera.
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
infra/teardown.sh rg-contoso-identity      # SP + app deleted, app purged from deleted items, group deleted
az ad app list --display-name "contoso orders API" --query "[].appId"   # []
```
Stop `run-api-local.sh` (Ctrl+C). The managed identity's service principal is removed with the identity; Learn notes
customers can't restore or permanently delete soft-deleted managed identity service principals — nothing to do.
