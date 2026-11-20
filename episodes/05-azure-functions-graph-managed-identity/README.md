# MG Lab #5 — Azure Functions + Microsoft Graph with managed identity (no secrets)

An HTTP-triggered Azure Function (.NET 8 isolated, Flex Consumption) reads the **Project Requests** SharePoint list
from [episode 3](../03-dataverse-vs-sharepoint/) through Microsoft Graph — with **no client secret** and access to
**exactly one site** (`Sites.Selected`).

| Path | What it is |
|---|---|
| [`src/MGLab.GraphFunction`](src/MGLab.GraphFunction) | `GET /api/requests?status=Approved` and `GET /api/whoami` (identity + roles in the token, never the token) |
| [`src/MGLab.GraphFunction.Tests`](src/MGLab.GraphFunction.Tests) | xUnit tests for the Graph field mapper (Kiota untyped values + JSON) |
| [`infra/main.bicep`](infra/main.bicep) | Storage (shared keys **off**), Flex plan, Function App, system + user-assigned identities, data-plane roles |
| [`infra/grant-graph-access.http`](infra/grant-graph-access.http) | The exact Graph calls: Sites.Selected app role + read on one site |
| [`deploy.sh`](deploy.sh) | Cloud Shell: Bicep → `dotnet publish` → zip deploy |

## Identities
- **System-assigned** → the Functions host's own storage (`AzureWebJobsStorage__accountName`).
- **User-assigned** (`GRAPH_CLIENT_ID`) → Microsoft Graph. Created by Bicep *before* the app runs, so you can grant
  Graph permissions before the first token is requested.

> ⚠️ **The 24-hour gotcha.** Managed identity tokens are cached by the platform per resource for ~24 hours and can't be
> force-refreshed. If the app requests a Graph token *before* you grant `Sites.Selected`, it keeps a token without roles
> (a restart didn't help in our demo). Grant first, then call.
> ([Microsoft Learn](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations#limitation-of-using-managed-identities-for-authorization))

## Run it
```bash
# Azure Cloud Shell (Bash)
git clone https://github.com/devladlog/mg-lab && cd mg-lab/episodes/05-azure-functions-graph-managed-identity
./deploy.sh <resource-group> "<host>,<site-collection-guid>,<web-guid>"
# then: infra/grant-graph-access.http (as an admin, e.g. in Graph Explorer)
```
Get the site id from `https://<tenant>.sharepoint.com/sites/<site>/_api/site/id` and `/_api/web/id`,
or `GET https://graph.microsoft.com/v1.0/sites/<tenant>.sharepoint.com:/sites/<site>`.

Locally: `az login`, copy `local.settings.sample.json` to `local.settings.json`, `func start`
(your own account needs access to the site).

## References
- [Managed identities for App Service and Azure Functions](https://learn.microsoft.com/azure/app-service/overview-managed-identity)
- [Flex Consumption plan](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan)
- [Sites.Selected — selected permissions in SharePoint](https://learn.microsoft.com/graph/permissions-selected-overview)
- [Create permission on a site](https://learn.microsoft.com/graph/api/site-post-permissions)
- [DefaultAzureCredential](https://learn.microsoft.com/dotnet/azure/sdk/authentication/credential-chains)
