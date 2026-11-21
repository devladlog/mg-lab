# Demo shot list — DEVLADLOG Deep Dive #3, Building secure business apps

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge for the Entra admin center, Azure portal and Power Apps; **SSMS**
for SQL. No Hyper-V VM is needed.

**Azure** (no subscription yet: this is the full list to provision; one resource group `rg-mglab-deep-dive-03`, West Europe)

| Resource | SKU | Estimated cost |
|---|---|---|
| App Service plan (Linux) | **F1 Free** | €0 (shared compute, no SLA; CPU quota, the app answers 403 when it's used up) |
| Web app `app-purchreq-<suffix>` | runs on the F1 plan, .NET 10, system-assigned identity | €0 |
| Azure SQL logical server `sql-purchreq-<suffix>` | Microsoft Entra-only authentication | €0 (no charge for the server itself) |
| Azure SQL database `purchase-requests` | **General Purpose serverless Gen5 2 vCores, free offer** (`useFreeLimit`, `AutoPause`) | €0 within 100,000 vCore seconds, 32 GB data, 32 GB backup per month; pauses instead of billing |
| Log Analytics workspace + Application Insights | PerGB2018, 30-day retention | pay per GB ingested; a recording session ingests a few MB, expect cents |

Total for one recording: **about €0 to €1**. Check the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/) on the day; delete the resource group right after.

**Microsoft 365 lab tenant**
- Users (lab, fictional): **Alex Demo** (requester), **Sam Demo** (approver and requester), **Jordan Demo**
  (approver + finance approver). Each needs a **Power Apps Premium** licence or trial, because custom connectors are
  premium. The maker (lab admin) too.
- Power Platform environment **`DEV`** (Dataverse not required for this episode, but it is the shared lab environment).
- Entra security group **`SQL Admins - Purchase Requests`** with the lab admin as member (it becomes the SQL Entra admin).
- Two app registrations (created in step 2): **Contoso Purchase Requests API** and **Contoso Purchase Requests Connector**.

**Local tools on the laptop:** Azure CLI, .NET SDK 10, Bicep CLI, SSMS (Entra MFA sign-in).

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 58 xUnit tests pass, `bicep build`/`lint` clean.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/03-building-secure-business-apps-azure-power-platfo
   dotnet test tests/PurchaseRequests.Tests -m:1          # expect Passed: 58
   ```
2. **API app registration** `Contoso Purchase Requests API` (single tenant):
   - *Expose an API* → Application ID URI `api://<client id>` → scope **`PurchaseRequests.ReadWrite`** (admins and
     users), display name "Read and write purchase requests".
   - *App roles* → create **Requester** (`Requester`), **Approver** (`Approver`), **Finance approver**
     (`Finance.Approver`), allowed member types *Users/Groups*.
   - *Manifest* → set `requestedAccessTokenVersion` (shown as `accessTokenAcceptedVersion` in the older manifest) to
     **2**. The API accepts v1 too, but v2 is what we expect; note in README which version the connector really got.
   - *Enterprise applications* → the same app → *Properties* → **Assignment required: Yes**. *Users and groups* →
     assign Alex → Requester; Sam → Approver **and** Requester; Jordan → Approver **and** Finance approver.
3. **Connector app registration** `Contoso Purchase Requests Connector` (single tenant): client secret (copy it into
   the connector, never on screen); *API permissions* → *My APIs* → Contoso Purchase Requests API → delegated
   `PurchaseRequests.ReadWrite` → **Grant admin consent**. The redirect URI comes in step 7.
4. **Azure**
   ```bash
   az login                                                     # lab account, off camera
   az group create -n rg-mglab-deep-dive-03 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-03 -f infra/main.bicep -p infra/main.bicepparam \
      -p apiClientId=<API client id> sqlAdminLogin="SQL Admins - Purchase Requests" \
         sqlAdminObjectId=$(az ad group show -g "SQL Admins - Purchase Requests" --query id -o tsv) \
      --query properties.outputs -o json > /tmp/purchreq-outputs.json     # don't show on camera
   dotnet publish src/PurchaseRequests.Api -c Release -o publish && (cd publish && zip -qr ../app.zip .)
   az webapp deploy -g rg-mglab-deep-dive-03 -n <webAppName> --src-path app.zip --type zip
   curl -s https://<webAppHostName>/healthz                     # "Healthy"; may be slow on the first call (F1)
   curl -s -o /dev/null -w "%{http_code}\n" https://<webAppHostName>/api/requests/mine   # 401
   ```
5. **SQL schema and grants** (SSMS, server `<sqlServerFqdn>`, *Microsoft Entra MFA*, database `purchase-requests`).
   Add your client IP to the server firewall for the session (portal → SQL server → Networking), remove it afterwards.
   - Run `sql/001-schema.sql`.
   - Open `sql/002-grant-app.sql`, set `@app` to the `webAppName` output, run it (record this: `grants-screen`).
     Expected result grid: the app as `EXTERNAL_USER` with `db_datareader` and `db_datawriter`; permissions grid:
     `DENY UPDATE` and `DENY DELETE` on `AuditEntries`.
6. **Custom connector** (make.powerapps.com, environment `DEV` → *Custom connectors* → *Import an OpenAPI file* →
   `connector/apiDefinition.swagger.json`, name `Contoso Purchase Requests`):
   General → Host = `webAppHostName`. Security → **OAuth 2.0**, identity provider **Microsoft Entra ID**, client ID and
   secret of the connector app, tenant ID = the lab tenant, Resource URL = `api://<API client id>`. Create, then copy
   the **Redirect URL** into the connector app registration (*Authentication* → *Web*).
7. **Test tab** → new connection as Alex → `ListMyRequests` must return `200 []`. A **401** means issuer or audience
   don't match (check the token version, step 2); a **403** means a missing scope consent or role assignment. Decode
   the token in a private window only if needed, never on camera.
8. **Canvas app** `Contoso Purchase Requests` (tablet layout), add the connector as data source. Formulas:
   - Screen *My requests*: `OnVisible` = `ClearCollect(colMine, ContosoPurchaseRequests.ListMyRequests())`;
     gallery `Items` = `colMine` showing `title`, `amount`, `status`.
   - *New request* button `OnSelect`:
     ```
     IfError(
         ContosoPurchaseRequests.SubmitRequest({title: txtTitle.Text, justification: txtWhy.Text,
             amount: Value(txtAmount.Text), currency: "EUR"}),
         Notify(FirstError.Message, NotificationType.Error),
         Notify("Submitted", NotificationType.Success); ClearCollect(colMine, ContosoPurchaseRequests.ListMyRequests()))
     ```
   - Screen *To decide* (visible to everyone; the API decides): gallery `Items` =
     `ContosoPurchaseRequests.ListPendingRequests()`; **Approve** button `OnSelect`:
     `IfError(ContosoPurchaseRequests.DecideRequest(ThisItem.id, {outcome: "Approve", comment: txtComment.Text}), Notify(FirstError.Message, NotificationType.Error), Notify("Approved", NotificationType.Success))`
     and a **Reject** button with `outcome: "Reject"`.
   - *Audit* panel: gallery `Items` = `ContosoPurchaseRequests.GetRequestAudit(galPending.Selected.id)`.
   Share the app with Alex, Sam and Jordan (they create their own connection on first run).
   **Check before recording:** what `FirstError.Message` shows for the 403 (the API's `detail` text "Requests above
   5,000 EUR need a finance approver." should be visible; note the real format in README).
9. **Dry run** the story once (Alex submits 7,500, Sam approves → refused, Jordan approves), then reset:
   `DELETE FROM dbo.PurchaseRequests;` as the SQL admin (the audit rows stay; use a fresh database or `TRUNCATE` as
   admin if you want an empty audit table for the take).

## Screens to capture (1920×1080, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `roles-screen` | `screens/entra-app-roles.jpg` | Entra admin center → Enterprise applications → *Contoso Purchase Requests API* → **Users and groups**: Alex Demo = Requester, Sam Demo = Approver and Requester (two rows), Jordan Demo = Approver and Finance approver (two rows). |
| `grants-screen` | `screens/sql-grants.jpg` | SSMS connected to `purchase-requests` as the Entra admin, `002-grant-app.sql` just executed: first grid shows the app identity (`EXTERNAL_USER`) with `db_datareader` and `db_datawriter`; second grid `DENY UPDATE` / `DENY DELETE` on `AuditEntries`. |
| `submit-screen` | `screens/app-submit.jpg` | Canvas app (play mode) signed in as **Alex**: "Two lab servers", 7,500 EUR just submitted, green "Submitted" banner, *My requests* shows it as **Pending**. |
| `decide-screen` | `screens/app-decide.jpg` | Canvas app as **Sam**: the 7,500 request selected, red banner with "Requests above 5,000 EUR need a finance approver." Then (second capture, same scene if the editor allows a cut) as **Jordan**: status **Approved**, audit panel with *Submitted* (Alex), *DecisionDenied* (Sam), *Approved* (Jordan). If only one image fits, use Jordan's view with the three audit rows. |

## Masking

Run `pipeline/mask.js` in the browser before capturing. Mask: tenant name and domain, user principal names (show
display names only), all GUIDs (client IDs, object IDs in the audit panel's `actorOid`), the web app and SQL host
names, the subscription name. Never show the connector's Security tab with the secret, `/tmp/purchreq-outputs.json`,
or an access token. In SSMS, hide the server name in the title bar/Object Explorer (collapse it or crop).

## Tear-down

```bash
az group delete -n rg-mglab-deep-dive-03 --yes --no-wait
```
Then delete the custom connector and the canvas app in `DEV`, the two app registrations (and their enterprise apps),
the `SQL Admins - Purchase Requests` group if it was created only for this episode, and the client-IP firewall rule
(gone with the resource group). Remove the Power Apps Premium trial assignments if they were added only for this.
