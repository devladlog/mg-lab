# DEVLADLOG Azure #2 — Cloud Architecture you can test

A small reference workload where the architecture is **code with tests**, not a diagram:

- **Governance first**: two built-in Azure Policy assignments at resource-group scope (allowed locations, required
  `workload` tag), deployed before anything else
- **Web app → private endpoints → data**: App Service (Linux, .NET 10) with VNet integration and a user-assigned
  managed identity; a storage account and a key vault with **public network access disabled**, reachable only through
  private endpoints + private DNS zones; shared keys off; Key Vault on Azure RBAC
- **Least privilege**: two data roles (Storage Blob Data Reader, Key Vault Secrets User), each on one resource
- **Operable**: one Log Analytics workspace, diagnostic settings on the blob service, the vault and the app;
  App Service Health check on `/healthz`, which checks both dependencies
- **One shape, two environments**: `lab` and `prod` differ only in values (SKU, instances, zone redundancy,
  replication, purge protection), kept in one `profiles` variable
- **Three layers of checks, all local**: 15 pytest guardrails on the compiled template, PSRule for Azure
  (Well-Architected rules) on both parameter files with **narrow, expiring exceptions**, 7 xUnit tests for the probe app

```
governance.bicep ─► Azure Policy (allowed locations, require tag)            all logs ─► Log Analytics
main.bicep
  network    VNet 10.50.0.0/24: snet-app (/26, delegated to Microsoft.Web/serverFarms), snet-pe (/26), NSGs
             privatelink.blob.<storage suffix>, privatelink.vaultcore.azure.net (linked to the VNet)
  data       storage (no public access, no keys) + key vault (RBAC, no public access) ─ private endpoints
  app        plan (B1 | P1v3 x2 zone-redundant) + web app (identity, VNet integration, /healthz) ─ 2 data roles
```

| Path | What it is |
|---|---|
| [`infra/governance.bicep`](infra/governance.bicep) | Policy assignments: Allowed locations (`e56962a6-…`), Require a tag on resources (`871b6d14-…`), with non-compliance messages |
| [`infra/main.bicep`](infra/main.bicep) | Composition + the `profiles` variable (lab / prod) |
| [`infra/modules/network.bicep`](infra/modules/network.bicep) | VNet, subnets (private, NSG, delegation), NSG rules against lateral SSH/RDP, private DNS zones + links |
| [`infra/modules/data.bicep`](infra/modules/data.bicep) | Storage + Key Vault + secret, private endpoints with DNS zone groups, diagnostic settings |
| [`infra/modules/app.bicep`](infra/modules/app.bicep) | Identity, role assignments, plan, web app (Health check path, TLS 1.2, FTPS off, ARR affinity off), FTP basic auth off |
| [`infra/modules/monitoring.bicep`](infra/modules/monitoring.bicep) | Log Analytics workspace |
| [`infra/env/*.bicepparam`](infra/env) | `lab`, `prod`, `governance` parameter files |
| [`infra/Invoke-Guardrails.ps1`](infra/Invoke-Guardrails.ps1) + [`ps-rule.yaml`](ps-rule.yaml) | PSRule for Azure over both parameter files; exit code 1 on any failure |
| [`.ps-rule/Suppressions.Rule.yaml`](.ps-rule/Suppressions.Rule.yaml) | The written-down exceptions: one per resource type and environment, each with a reason and `expiresOn` |
| [`tests/guardrails`](tests/guardrails) | 15 pytest tests on `bicep build` output (main + governance) and `bicep build-params` |
| [`src/ReadinessProbe`](src/ReadinessProbe) | .NET 10 minimal API: `/` and `/healthz` (ASP.NET Core health checks for blob + secret, 5 s timeout each, options validated at startup) |
| [`tests/ReadinessProbe.Tests`](tests/ReadinessProbe.Tests) | 7 xUnit tests with `WebApplicationFactory` and faked SDK clients |
| [`infra/deploy.sh`](infra/deploy.sh) | Governance → what-if → workload → publish probe → curl `/healthz` |
| [`infra/try-policy.sh`](infra/try-policy.sh) | Two requests that the policies must deny |
| [`infra/prove-private.sh`](infra/prove-private.sh) | From outside: DNS, refused data-plane calls; then the app's `/healthz` |
| [`infra/teardown.sh`](infra/teardown.sh) | Delete the group, purge the (lab) vault |

## Run the checks (here, no Azure needed)

```bash
python3 -m pytest tests/guardrails -q          # 15 passed (Bicep CLI 0.49.2)
dotnet test tests/ReadinessProbe.Tests          # Passed!  - Failed: 0, Passed: 7, Total: 7

# PSRule for Azure (modules saved to a local folder for this run: PSRule 2.9.0, PSRule.Rules.Azure 1.47.0)
pwsh -c 'Save-Module PSRule.Rules.Azure -Path /tmp/psmodules -Repository PSGallery'   # outside the repo
PSModulePath=/tmp/psmodules pwsh infra/Invoke-Guardrails.ps1
#   lab   pass  118   fail   0   suppressed   6
#   prod  pass  123   fail   0   suppressed   1

cd infra && bicep lint main.bicep && bicep lint governance.bicep     # clean, bicepconfig.json rules at error
bash -n deploy.sh try-policy.sh prove-private.sh teardown.sh
```

Also verified here: `dotnet publish` of the probe (5.3 MB), a mutation check (switching the storage account to
`publicNetworkAccess: 'Enabled'` makes `test_storage_is_private_and_keyless` fail in 1.5 s), and that an expired
suppression stops applying (moving the prod `expiresOn` into the past makes `Azure.Log.Replication` fail again).
**Not run here:** anything in Azure. See [demo.md](demo.md).

## Deploy, prove, tear down (needs a subscription)

```bash
az login
infra/deploy.sh rg-contoso-arch swedencentral lab
infra/try-policy.sh rg-contoso-arch westeurope      # both requests: RequestDisallowedByPolicy
infra/prove-private.sh rg-contoso-arch
infra/teardown.sh rg-contoso-arch
```

## What we learned / gotchas

- **A broad suppression hides real findings.** The first exception file matched only `tags.environment == lab`.
  PSRule then reported **78** suppressed results: all six rules against every lab resource. Now each group targets
  one resource type plus the environment (6 suppressed in lab, 1 in prod), and every group has `expiresOn`.
- **The first PSRule run on prod found six things.** Fixed: outbound deny of SSH/RDP to the VNet on both NSGs
  (`Azure.NSG.LateralTraversal`), `defaultOutboundAccess: false` on both subnets (`Azure.VNET.PrivateSubnet`),
  `clientAffinityEnabled: false` (`Azure.AppService.ARRAffinity`). Application Insights was dropped, which also cleared
  `Azure.AppInsights.LocalAuth`: the probe has no telemetry SDK, and its logs reach the workspace through diagnostic
  settings. Kept as an expiring exception: `Azure.Log.Replication` (workspace replication waits for a DR-region decision).
- **The Bicep linter rejects `privatelink.blob.core.windows.net`** (`no-hardcoded-env-urls`). The zone name is built
  from `environment().suffixes.storage`, so the template also works in other clouds. The Key Vault zone stays literal.
- **Misconfiguration must fail at startup.** The first probe threw inside the health check factory, so `/healthz`
  returned a 500 with a stack trace. Options are now validated with `ValidateOnStart()`; a test pins it.
- **Faking Azure SDK clients: override every overload you might hit.** `GetSecretAsync(name, cancellationToken: ct)`
  binds to the newer overload with `outContentType` in Azure.Security.KeyVault.Secrets 4.12. The fake only overrode
  the older one, so the base class ran with no pipeline and threw `NullReferenceException`.
- **`.bicepparam` names its template.** With a Bicep parameters file, don't pass `--template-file` as well; the Azure
  CLI rejects the combination (Learn: "Only a .bicep file is allowed with a .bicepparam file").
- **Route-all is off on purpose.** Without it, only private (RFC1918) traffic goes into the VNet, which is all the
  private endpoints need; internet egress isn't forced through private subnets that have no NAT gateway.
- **Health check on one instance only monitors.** App Service reroutes traffic away from unhealthy instances only when
  there are at least two; the lab's single B1 instance gets the monitoring, prod's two instances get the rerouting.
- **Policy isn't instant.** A new assignment takes about five minutes to apply to the scope; `deploy.sh` deploys
  governance first and the demo waits before testing the deny.

## References
- Blog: [Cloud Architecture — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-01-cloud-architecture-complete-guide-2026/)
- [What is the Azure Well-Architected Framework?](https://learn.microsoft.com/azure/well-architected/what-is-well-architected-framework) and [the pillars](https://learn.microsoft.com/azure/well-architected/pillars)
- [Reliability in Azure App Service](https://learn.microsoft.com/azure/reliability/reliability-app-service) (zone redundancy: Premium v2–v4, at least two instances)
- [Monitor App Service instances by using Health check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check)
- [Enable virtual network integration in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-vnet-integration-enable) and [routing](https://learn.microsoft.com/azure/app-service/configure-vnet-integration-routing)
- [Azure Private Endpoint private DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)
- [Default outbound access in Azure](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [Azure built-in roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles) (Storage Blob Data Reader, Key Vault Secrets User)
- [Provide access to Key Vault with Azure RBAC](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Azure Policy built-in definitions](https://learn.microsoft.com/azure/governance/policy/samples/built-in-policies) and [tag policies](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-policies)
- [Get compliance data: evaluation triggers](https://learn.microsoft.com/azure/governance/policy/how-to/get-compliance-data#evaluation-triggers) (about five minutes for a new assignment)
- [Deploy Bicep files with the Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-cli#parameters) and [Bicep parameters files](https://learn.microsoft.com/azure/azure-resource-manager/bicep/parameter-files)
- [Enable Key Vault logging](https://learn.microsoft.com/azure/key-vault/general/howto-logging)
- [Quickstart: Deploy an ASP.NET web app](https://learn.microsoft.com/azure/app-service/quickstart-dotnetcore) (`DOTNETCORE:10.0`, `az webapp deploy`)
- PSRule for Azure (not on Learn): https://azure.github.io/PSRule.Rules.Azure/
