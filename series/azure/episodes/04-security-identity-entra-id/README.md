# DEVLADLOG Azure #4 — Security & Identity with Entra ID: an API with zero secrets

Episode 1's order processor and episode 3's pipeline both signed in without a secret. This episode looks at what
that identity really is, and protects the contoso **orders API** the same way:

- **Entra objects as code** with the **Microsoft Graph Bicep extension**: the API's app registration, its service
  principal, a user-assigned **managed identity** for the order processor, and the app role assignments — next to
  Azure resources in one template, with no client secret or certificate anywhere
- **Two kinds of callers, two kinds of permission**: people call through a client with the delegated scope
  `Orders.Read` (`scp` claim); workloads call as themselves with the app role `Orders.ReadWrite.All` (`roles` claim)
- **The API decides with claims, not hope**: Microsoft.Identity.Web validates the token (signature, issuer,
  lifetime, audience = the API's client ID); policies read `scp`, `roles` and the `idtyp` optional claim, so a user
  token that somehow carries the app role still can't write
- **Assignment required** on the service principal: an identity without an app role assignment doesn't get a token
- **Proof without secrets**: a container with the managed identity reads its own token from the instance metadata
  service and prints the claims (never the token)

```
 Alex Demo ─(Azure CLI, delegated)──► token: aud=API client ID, scp=Orders.Read, roles=[Orders.Reader]
                                            └─► GET /orders 200 · POST /orders 403
 order processor ─(managed identity)─► token: aud=API client ID, roles=[Orders.ReadWrite.All], idtyp=app
                                            └─► POST /orders 201 (createdBy = its client ID)
 identity.bicep (Graph extension): app registration (v2 tokens, api://{tenantId}/contoso-orders, idtyp claim)
                                   + service principal (assignment required) + managed identity + 2 assignments
```

| Path | What it is |
|---|---|
| [`infra/identity.bicep`](infra/identity.bicep) | Graph Bicep: application, service principal, `appRoleAssignedTo` ×2 (processor, readers); Azure: the managed identity |
| [`infra/bicepconfig.json`](infra/bicepconfig.json) | `microsoftGraphV1` → `br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:1.0.0`, linter rules at error |
| [`infra/env/lab.bicepparam`](infra/env/lab.bicepparam) | Lab values; no object IDs committed (deploy.sh passes yours inline) |
| [`infra/deploy.sh`](infra/deploy.sh) | what-if → deploy → outputs (IDs only) to `~/.contoso-orders/outputs.json` |
| [`infra/lab-preauthorize-cli.sh`](infra/lab-preauthorize-cli.sh) | **Lab only**: pre-authorizes the Azure CLI for `Orders.Read` (Graph PATCH, merged into the `api` block) |
| [`infra/run-api-local.sh`](infra/run-api-local.sh) / [`infra/call-as-user.sh`](infra/call-as-user.sh) | Run the API against the real tenant; call it as yourself (claims, then GET 200 / POST 403) |
| [`infra/prove-app-token.sh`](infra/prove-app-token.sh) | Short-lived container instance with the managed identity → claims of its token from IMDS |
| [`infra/teardown.sh`](infra/teardown.sh) | Deletes the service principal and app, purges the app from deleted items, deletes the group |
| [`src/Contoso.Orders.Api`](src/Contoso.Orders.Api) | .NET 10 minimal API, Microsoft.Identity.Web 4.18.0, policies in [`AuthPolicies.cs`](src/Contoso.Orders.Api/AuthPolicies.cs) |
| [`src/Contoso.Orders.Client`](src/Contoso.Orders.Client) | The order processor: `EntraTokenHandler` (any `TokenCredential`, `/.default` scope), managed identity in Azure, Azure CLI on a laptop |
| [`tools/claims.py`](tools/claims.py) | Prints the authorization claims of a token (stdin or IMDS), never the token |
| [`tests/Contoso.Orders.Tests`](tests/Contoso.Orders.Tests) | 20 xUnit tests: the real API pipeline with test-signed tokens + the client handler |
| [`tests/python`](tests/python) | 21 pytest tests: compiled Graph Bicep guardrails, `claims.py` (fake IMDS), the tenant scripts with a fake `az` |

## Run it here (no tenant)

```bash
dotnet test tests/Contoso.Orders.Tests --artifacts-path /tmp/orders-artifacts   # Passed! - Failed: 0, Passed: 20
python3 -m pytest tests/python -q                                               # 21 passed
cd infra && bicep lint identity.bicep && bicep build identity.bicep --stdout > /dev/null
```

Verified in this container (.NET SDK 10, Bicep CLI 0.49.2 with the Graph extension restored from MCR, Python 3,
pytest 9.1.1): 20 xUnit + 21 pytest passed, lint clean, build and build-params without warnings. The API also
started locally (`/healthz` 200, `/orders` without a token 401 with `WWW-Authenticate: Bearer`). Mutation check:
removing `.RequireClaim("idtyp", "app")` from the write policy makes exactly the two tests that guard it fail.

How the API tests work: `ApiFactory` keeps Microsoft.Identity.Web's configuration (audience validation, the
scope/role checks) and only swaps the signing key and issuer check for a local RSA test key, because the real
keys come from the tenant's OpenID metadata. **Not run here:** anything against Entra ID or Azure (deployment,
real tokens, the container instance). See [demo.md](demo.md).

## Run it against the lab tenant (needs tenant)

```bash
az login
infra/deploy.sh rg-contoso-identity swedencentral
infra/lab-preauthorize-cli.sh                 # lab only
infra/run-api-local.sh &                      # http://localhost:5080
infra/call-as-user.sh                         # claims, GET /orders 200, GET /me, POST /orders 403
infra/prove-app-token.sh rg-contoso-identity  # aud = API client ID, roles = [Orders.ReadWrite.All], idtyp = app
infra/teardown.sh rg-contoso-identity
```

## What we learned / gotchas

- **`api://{appId}` is the recommended App ID URI, but a template can't reference the app's own appId while
  creating it.** We use `api://{tenantId}/contoso-orders`, which is on Learn's list of secure patterns, with the
  tenant ID from `tenant().tenantId`. Arbitrary `api://name` values can be refused by the identifier URI policy,
  which Microsoft may already have enabled in your tenant.
- **v2.0 tokens: the audience is the API's client ID.** With `requestedAccessTokenVersion: 2`, `aud` is always the
  client ID; in v1.0 tokens it can be the App ID URI. Our API configures only `ClientId`, and a token whose `aud` is
  the App ID URI is rejected (test `Wrong_audience_is_401`). Learn's advice for apps with custom URIs: use v2.0
  tokens and accept only the appId.
- **`roles` isn't proof of an application.** Users can carry app roles too (our `Orders.Reader`), so the write
  policy also requires the `idtyp` optional claim to be `app`, which Entra emits only on app-only tokens by default.
  A test proves a user token carrying `Orders.ReadWrite.All` still gets 403.
- **No `scp` and no `roles` = 401.** Microsoft.Identity.Web rejected a valid, correctly signed token that had
  neither claim (test `Token_without_scp_or_roles_is_rejected`) — what a managed identity without an app role
  assignment would present (with assignment required it shouldn't get a token at all).
- **App-only calls ask for `{App ID URI}/.default`.** You can't request one app role; the token carries every role
  assigned to the identity. `EntraTokenHandler` refuses any other scope at construction.
- **A misplaced Graph property is only a warning.** Putting `requestedAccessTokenVersion` at the top level (instead of
  under `api`) gives BCP037 and the build still succeeds. We tried to raise it to an error in `bicepconfig.json`
  (under the linter rules and under a `diagnostics` key); neither worked with Bicep 0.49.2. So the template tests
  fail on any build warning.
- **Deleting the resource group doesn't delete the app.** Entra objects aren't in the group. Deleted app
  registrations stay restorable for 30 days, and redeploying the same `uniqueName` after a deletion outside Bicep
  fails ("Another object with the same value for property uniqueName already exists", a documented known issue).
  `teardown.sh` deletes the service principal and the app, then permanently deletes the app from deleted items.
- **Pre-authorizing the Azure CLI is a lab shortcut.** It's documented for tools that need `az account
  get-access-token`, but it lets anyone assigned to the API use the CLI as the client. Real clients get their own app
  registration. The next Bicep deployment removes the pre-authorization, because the template owns the `api` block.

## References
- Blog: [Security & Identity (Entra ID) — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-19-security-identity-entra-id-complete-guide-2026/)
- [Bicep templates for Microsoft Graph resources](https://learn.microsoft.com/graph/templates/bicep/overview-bicep-templates-for-graph), [quickstart](https://learn.microsoft.com/graph/templates/bicep/quickstart-create-bicep-interactive-mode) (v1.0 extension `1.0.0`), [v1.0 reference](https://learn.microsoft.com/graph/templates/bicep/reference/overview?view=graph-bicep-1.0), [appRoleAssignedTo](https://learn.microsoft.com/graph/templates/bicep/reference/approleassignedto?view=graph-bicep-1.0), [servicePrincipals](https://learn.microsoft.com/graph/templates/bicep/reference/serviceprincipals?view=graph-bicep-1.0) and [known issues](https://learn.microsoft.com/graph/templates/known-issues-graph-bicep)
- [Restrictions on identifier URIs](https://learn.microsoft.com/entra/identity-platform/identifier-uri-restrictions) and [security best practices for application properties](https://learn.microsoft.com/entra/identity-platform/security-best-practices-for-app-registration)
- [Access token claims reference](https://learn.microsoft.com/entra/identity-platform/access-token-claims-reference) (`aud` in v1.0 vs v2.0) and [optional claims reference](https://learn.microsoft.com/entra/identity-platform/optional-claims-reference) (`idtyp`)
- [Secure applications and APIs by validating claims](https://learn.microsoft.com/entra/identity-platform/claims-validation)
- [Microsoft.Identity.Web authorization](https://learn.microsoft.com/entra/msidweb/authentication/authorization) (`RequiredScopeOrAppPermission`) and [protected web API: verify scopes and app roles](https://learn.microsoft.com/entra/identity-platform/scenario-protected-web-api-verification-scope-app-roles)
- [Quickstart: daemon app calling a web API](https://learn.microsoft.com/entra/identity-platform/quickstart-daemon-app-call-api) (app roles with member type Applications, `idtyp`)
- [Assign an app role to a managed identity](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/assign-app-role-managed-identity-azure-cli)
- [Use managed identities with Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-managed-identity) (IMDS token request)
- [az account get-access-token](https://learn.microsoft.com/cli/azure/account#az-account-get-access-token) (`--scope`) and [Commonly used Microsoft first-party apps](https://learn.microsoft.com/power-platform/admin/apps-to-allow) (Azure CLI app ID)
- [Restore or remove a recently deleted application](https://learn.microsoft.com/entra/identity-platform/howto-restore-app) and [Recover from deletions](https://learn.microsoft.com/entra/architecture/recover-from-deletions)
- [Deploy Bicep files with the Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-cli#parameters) (`.bicepparam` + inline overrides)
- [Workload identity federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) (the mechanism behind episode 3's service connection)
