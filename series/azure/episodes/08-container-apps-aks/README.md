# DEVLADLOG Azure #8 — Container Apps & AKS: one image, scale to zero or pay for a node

Episodes 1–7 ran contoso's order services as functions, App Service and a database-backed API. This episode puts the
stateless **order-pricing API** (episode 1's catalogue and 5 %-from-500-EUR rule, `POST /quotes`) in a container and runs
the **same image** on both platforms, so the differences are the platforms', not the code's:

- **Azure Container Apps, Consumption plan (the main demo).** ACR Basic with the **admin user off**; the app pulls with a
  **user-assigned managed identity** (AcrPull). Workload-profiles environment with only the Consumption profile.
  **Multiple revision mode**, HTTP scale rule (20 concurrent requests per replica), **0–3 replicas**, probes on the app's
  own endpoints. v1.0.0 and v1.1.0 side by side with a traffic split
- **AKS in its smallest real form (comparison).** Free-tier control plane, **one** `Standard_D4as_v5` system node, the
  kubelet identity with AcrPull on the same registry. Deployment (2 replicas, probes, locked-down security context), a
  `LoadBalancer` Service, an HPA (2–5) and a PodDisruptionBudget. Created for the AKS scenes and deleted right after
- **An app that behaves on both.** `/healthz/live` (never checks dependencies), `/healthz/ready` (503 while warming up and
  while draining), SIGTERM handling (readiness flips to 503 first, 5 s drain, 25 s host shutdown = the 30 s both platforms
  allow), `GET /` reporting version, platform (`container-apps` / `kubernetes`), revision and replica
- **No Dockerfile, no Docker daemon.** The image is built by the .NET SDK (`dotnet publish /t:PublishContainer`), to a
  tarball in the tests and straight into ACR in the demo

```
 dotnet publish /t:PublishContainer ──► ACR Basic (admin off) ◄── AcrPull ── user-assigned identity ◄── Container App (0..3 replicas)
        │ token: az acr login --expose-token                          │            ingress ─► revision v1-0-0 (80 %) / v1-1-0 (20 %)
        └─ base image imported into the same registry                 └── AcrPull ── kubelet identity ◄── AKS Free tier, 1 node, 2 pods
 load.py ─► HTTP rule: requests in the last 15 s / 15 vs 20 ─► 1..3 replicas ─► 300 s cool-down ─► 0
```

| Path | What it is |
|---|---|
| [`src/Contoso.Orders.Api`](src/Contoso.Orders.Api) | Minimal API (.NET 10): `POST /quotes`, `GET /`, `/healthz/live`, `/healthz/ready`; [`Pricing.cs`](src/Contoso.Orders.Api/Pricing.cs), [`Lifecycle.cs`](src/Contoso.Orders.Api/Lifecycle.cs) (readiness state, SIGTERM drain), container settings in the `.csproj` |
| [`infra/aca.bicep`](infra/aca.bicep) + [`.bicepparam`](infra/aca.bicepparam) | Log Analytics (1 GB/day cap), ACR Basic, identity + roles (AcrPull for the app, AcrPush for you), environment, container app (created only when `deployApp=true`) |
| [`infra/aks.bicep`](infra/aks.bicep) + [`.bicepparam`](infra/aks.bicepparam) | AKS Free tier, one 4-vCPU system node, 64 GB managed OS disk, kubelet AcrPull |
| [`k8s/*.yaml`](k8s) | Deployment, Service (LoadBalancer), HPA, PodDisruptionBudget |
| [`infra/deploy-aca.sh`](infra/deploy-aca.sh) | Register providers → phase 1 (registry, environment) → push 1.0.0 → what-if → phase 2 (app) → wait for the first answer |
| [`infra/push-image.sh`](infra/push-image.sh) | Import the base image into the registry, build and push with the SDK using an Entra token (no Docker) |
| [`infra/release-v2.sh`](infra/release-v2.sh) / [`split.sh`](infra/split.sh) | Pin v1-0-0 to 100 %, push 1.1.0, new revision, 80/20 split; count which version answered N requests |
| [`infra/load.py`](infra/load.py) / [`replicas.sh`](infra/replicas.sh) | Parallel `POST /quotes` from N threads (stdlib only); replica count per active revision every 30 s |
| [`infra/deploy-aks.sh`](infra/deploy-aks.sh) | Quota check → cluster → server-side dry run → apply the manifests → rollout → public IP → `GET /` |
| [`infra/teardown.sh`](infra/teardown.sh) | `--aks-only` right after the AKS scenes; otherwise delete the whole group |
| [`tests/Contoso.Orders.Api.Tests`](tests/Contoso.Orders.Api.Tests) | 9 xUnit tests |
| [`tests/infra`](tests/infra) | 29 pytest tests: both Bicep files, the manifests, the **real image**, `load.py`, `script.yaml` |

## Build and test (here, no Azure needed)

```bash
dotnet test tests/Contoso.Orders.Api.Tests -m:1
#   Passed!  - Failed: 0, Passed: 9, Skipped: 0, Total: 9
#   quote discount from 500 EUR, 400/422 rejections, version header + platform, probes on their own paths,
#   warm-up 503 -> ready, drain wins over everything, SIGTERM flips /healthz/ready to 503 while /healthz/live keeps answering

python3 -m pytest tests/infra -q                  # 29 passed
#   test_aca 9    registry (Basic, admin off, ARM-audience policy), pull identity + AcrPull, app only in phase 2, Consumption
#                 profile, Multiple mode + 8080, scale to zero + HTTP rule, probes, log cap, no secrets
#   test_aks 3    Free tier, 1 node of >= 4 vCPU and not B-series, kubelet AcrPull
#   test_k8s 7    probes = Container Apps' probes, locked down, requests/limits, maxUnavailable 0, drain fits the grace period,
#                 Service/HPA/PDB point at the Deployment, image placeholder
#   test_image 3  builds the REAL image tarball with the SDK (no Docker) and checks port 8080, numeric user 1654, version label
#   test_load 2   load.py against a local stand-in server (tests only; the demo runs it against the real app)
#   test_script 5 script.yaml: header, 12-16 scenes, 750-900 words, 3 shorts, every code line exists in this folder

cd infra
bicep lint aca.bicep && bicep lint aks.bicep      # clean (bicepconfig.json rules at error)
PUSHER_OBJECT_ID=00000000-0000-0000-0000-000000000000 bicep build-params aca.bicepparam --stdout > /dev/null
ACR_NAME=acrexample bicep build-params aks.bicepparam --stdout > /dev/null
for f in *.sh; do bash -n $f; done
```

Verified in this container: .NET SDK 10.0.115, Bicep 0.49.2, pytest 9.1.1 (dotnet restore needs the NuGet feed).
Also run here, by hand: the published app on localhost: `/healthz/ready` is 503 for the first three seconds then 200; after
`kill -TERM`, ready stays 503 and live 200 during the 5 s drain, then the process exits; the quote for 2 x MON-270 +
1 x DOC-100 returns subtotal 568.98, discount 28.45, total 540.53. The image tarball's config shows
`ExposedPorts 8080/tcp`, `ASPNETCORE_HTTP_PORTS=8080`, `User 1654`.

**Not run here (needs the lab subscription, see demo.md):** everything on Azure — deployment, managed-identity pull, scale
out and in, revisions and the traffic split, AKS, `kubectl apply --dry-run=server`. `kubectl` is not installed here, so the
manifests are checked as YAML by tests, not by a cluster. `load.py` has never run against a real app.

## Cost (Azure Retail Prices API, EUR, list prices, West Europe, queried 21 Nov 2026)

| Item | Price | Note |
|---|---|---|
| Container Apps Consumption | free grants per subscription and month: 180,000 vCPU-s, 360,000 GiB-s, 2 M requests | No usage charge at zero replicas. The API rounds the per-second meters to 0.0, so don't price from it: stay inside the grants (the recording uses a few hundred vCPU-seconds) |
| ACR Basic | 0.1496 / day | billed per registry-day |
| AKS Free tier control plane | 0 | no financially backed uptime SLA |
| `Standard_D4as_v5` Linux node | 0.1867 / h | busy or idle |
| Standard load balancer | 0.0224 / h | rows are under location *Global*, not westeurope |
| 2 x Standard static public IPv4 | 2 x 0.0045 / h | outbound + the Service's address |
| P6 managed OS disk (64 GB) | 10.0787 / month = 0.0138 / h | |
| **AKS node + disk + LB + IPs** | **about 0.232 / h** | 0.46 for two hours; **about 5.6 for a day; about 170 for a month, against a 30 EUR budget** |

## What we learned / gotchas

- **The HTTP scale rule isn't "parallel connections".** Learn: every 15 seconds, the requests of the last 15 seconds are
  divided by 15 and compared with `concurrentRequests` (default 10, we use 20). A fast endpoint needs a rate, not a
  crowd, to scale: `load.py` uses 24 threads for that reason.
- **Scale to zero has a delay.** Cool-down is 300 s, only applies from the last replica to 0; scale-in removes 100 % of the
  replicas that need to go. Scale-out steps 1, 4, 8, 16... up to `maxReplicas`.
- **Replicas get SIGTERM and 30 seconds.** Learn: SIGKILL follows if the app doesn't answer in 30 s (the template property
  `terminationGracePeriodSeconds` defaults to 30). Hence 5 s drain + 25 s `HostOptions.ShutdownTimeout`, and Kubernetes'
  `terminationGracePeriodSeconds: 30`, which a test pins.
- **Managed-identity pull needs the registry to accept ARM-audience tokens.** Learn's prerequisite
  (`az acr config authentication-as-arm`); the Bicep sets `azureADAuthenticationAsArmPolicy`, a test pins it. Learn's App Service
  page shows the symptom when it is off: `UNAUTHORIZED` "token validation failed" (not tried on Container Apps).
- **The .NET SDK's env-var credentials apply to the source and the destination registry.** Learn's own warning. We import
  `mcr.microsoft.com/dotnet/aspnet:10.0` into our registry (`az acr import`, no Docker) so one token covers both. The
  username for an ACR access token is the all-zero GUID (Learn, ACR authentication).
- **Two-phase deployment.** The container app references an image that must exist, so the template creates the registry
  and environment first (`deployApp=false`), the script pushes, then `deployApp=true` creates the app (design choice;
  the single-pass failure itself was not tried).
- **A "latest revision 100 %" ingress rule hands a new revision all traffic as soon as it is ready.** Learn's "Update existing
  revision" scenario pins the known-good revision first; `release-v2.sh` does that, so v1-1-0 starts at 0 % and gets 20 % on
  purpose. (The behaviour of the unpinned case is reasoned from the rule, not observed.)
- **.NET images run as UID 1654 and listen on 8080.** Confirmed from the real image config here: `runAsNonRoot` in the
  manifest works because the user is numeric; the probes, ingress target port and Service target port are all 8080. With a
  read-only root file system the pod needs a writable `/tmp` (an `emptyDir` in the manifest).
- **AKS: one node is a lab shortcut.** Learn: system pools need a VM of at least 4 vCPUs and 4 GB, no B-series, and "must
  contain at least two nodes" (three recommended; a production single system pool needs at least two). The Free tier is
  for dev/test: no uptime SLA, recommended below 10 nodes. We keep one `Standard_D4as_v5` for under two hours and delete
  it; a real cluster uses the Standard tier and more nodes. `deploy-aks.sh` checks the 4-vCPU DASv5 quota first.
- **Retail Prices API: zero rows is not zero euros.** The load balancer meters only appeared with `location eq 'Global'`
  (our first region filter returned nothing), and the Container Apps per-second meters round to 0.0. Both are traps for
  automated pricing (episode 6 has the same rule).
- **Learn: enable data protection for .NET apps on Container Apps.** Not needed here (no cookies, no antiforgery, stateless
  quotes), but it applies as soon as a replica must read another replica's protected data.

## References
- Blog: [Container Apps & AKS — Complete Guide](https://www.devladlog.com/articles/azure/2026-02-03-container-apps-aks-complete-guide-2026/)
- [Billing in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/billing) (monthly free grants, no charge at zero replicas, health probes not billable, plan management fee only for Dedicated)
- [Set scaling rules in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/scale-app) (HTTP rule math, defaults, cool-down 300 s, scale steps, data protection note)
- [Application lifecycle management](https://learn.microsoft.com/azure/container-apps/application-lifecycle-management) (SIGTERM, SIGKILL after 30 s)
- [Traffic splitting](https://learn.microsoft.com/azure/container-apps/traffic-splitting) and [revisions](https://learn.microsoft.com/azure/container-apps/revisions) (multiple revision mode, weights, "update existing revision")
- [Image pull with managed identity](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull) (AcrPull, ARM audience tokens, user-assigned preferred)
- [Authenticate with Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) (`az acr login --expose-token`, all-zero GUID username)
- [Containerize a .NET app with dotnet publish](https://learn.microsoft.com/dotnet/core/containers/sdk-publish) (tarball without a daemon), [SDK container overview](https://learn.microsoft.com/dotnet/core/containers/overview) (`DOTNET_CONTAINER_REGISTRY_UNAME/PWORD`, same credentials for both registries), [container properties](https://learn.microsoft.com/dotnet/core/containers/publish-configuration)
- [AKS pricing tiers](https://learn.microsoft.com/azure/aks/free-standard-pricing-tiers) (Free: dev/test, < 10 nodes, no SLA) and [system node pools](https://learn.microsoft.com/azure/aks/use-system-pools) (4 vCPU / 4 GB, no B-series, at least two nodes, `MC_` group deleted with the cluster)
- Prices: [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (EUR, West Europe, queried 21 Nov 2026)
