# DEVLADLOG Deep Dive #10: Cloud-native application platform (AKS, Dapr, KEDA, Service Bus)

In episode 7, Contoso's gateway put every purchase of 5,000 EUR or more on the `finance-review` subscription of the
`purchase-events` topic. Who drains it? A small worker on Kubernetes: **Dapr** delivers the messages to the app through a
sidecar (no Service Bus SDK in the code), **KEDA** scales the worker from zero to ten replicas from the subscription's
backlog, and **workload identity** replaces every connection string. This episode builds that platform and tests the
parts that must agree with each other.

```
APIM (ep 7) ─► Service Bus Standard: topic purchase-events ─► subscription finance-review (label purchase.high)
                                                                   │  ▲ message counts (KEDA identity, Data Owner on the namespace)
                                   Dapr sidecar (consumerID = finance-review, Entra auth, no entity management)
                                                                   ▼  │
   AKS Free tier: namespace contoso-finance ── Deployment finance-worker (app + daprd) ◄── KEDA ScaledObject 0..10
   workload identity: SA finance-worker ─► id-worker (Data Receiver on the topic);  SA kube-system/keda-operator ─► id-keda
   kubelet ─► AcrPull on ACR Basic (admin user off)
```

| Path | What it is |
|---|---|
| [`src/FinanceReview.Worker`](src/FinanceReview.Worker) | .NET 10 minimal API. `GET /dapr/subscribe` (raw payload), `POST /finance-review` decodes the CloudEvent (`data_base64` or `data`), validates with episode 7's rules, answers `200 {"status":"SUCCESS"/"RETRY"/"DROP"}`. `Dockerfile` (chiseled base, UID 1654) |
| [`deploy/`](deploy) | Namespace + service account (workload identity annotation), Dapr `Component` (`pubsub.azure.servicebus.topics`), Deployment (Dapr annotations, hardened, no `replicas`), KEDA `TriggerAuthentication` + `ScaledObject`. `{{tokens}}` are filled from the Bicep outputs |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | Service Bus Standard (topic, `finance-review` + label filter), ACR Basic, AKS Free tier (OIDC issuer, workload identity, KEDA add-on, 2 nodes), Dapr extension (no HA), two identities with federated credentials, three role assignments |
| [`scripts/render_manifests.py`](scripts/render_manifests.py) | Fills `deploy/*.yaml` from `az deployment group show` outputs; refuses a missing value |
| [`scripts/send_burst.py`](scripts/send_burst.py) | Sends N purchase events (plus optional invalid ones) to the topic with the Service Bus REST API and an Entra token |
| [`tests/FinanceReview.Tests`](tests/FinanceReview.Tests) | 21 xUnit tests: decoding, decisions, the real ASP.NET Core pipeline in memory |
| [`tests/contracts`](tests/contracts) | 31 pytest tests: compiled Bicep (real `bicep build`) against the manifests, the code and the scripts |

## Test locally (no Azure, no cluster)

```bash
dotnet test tests/FinanceReview.Tests -m:1            # Passed: 21 (about 40 s including restore)
python3 -m pytest tests/contracts -q                  # 31 passed (about 3 s; needs PyYAML, pytest, bicep on the PATH)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # clean
bicep build-params infra/main.bicepparam --stdout > /dev/null
```

What is proven, and what is not:

- **The worker** was also published (`dotnet publish -c Release`, the same commands as the Dockerfile) and **run**: `/healthz`,
  `/dapr/subscribe`, and two `curl` posts with `Content-Type: application/cloudevents+json` returned `{"status":"SUCCESS"}` and
  `{"status":"DROP","reason":"..."}`, with one readable log line each. There is no Docker daemon in this container, so the
  **Dockerfile itself was never built** (the demo builds it with `az acr build`).
- **Contract tests** catch drift between files: one subscription name in Bicep, Dapr `consumerID` and KEDA `subscriptionName`;
  topic and component names equal to the constants in `Program.cs`; the federated-credential subjects equal the manifest's service
  account and `kube-system:keda-operator`; no connection string or secret anywhere; Service Bus is Entra-only; exactly three role
  assignments with the right scopes; the Deployment has no `replicas` field; `maxActiveMessages` stays within twice KEDA's `messageCount`;
  `ASPNETCORE_HTTP_PORTS` matches `dapr.io/app-port`. Bicep names are resolved by a small ARM-expression evaluator in `conftest.py`.
- **Not proven here:** that AKS, the Dapr extension, KEDA and Service Bus accept this configuration and behave as the tests assume.
  There is no kubeconform or cluster in the container: manifests are checked structurally and against the documented field names, not
  against the CRD schemas. The deployment was not run (no Azure access). See "Not verified" below.

Tested with .NET SDK 10.0.115, `Microsoft.AspNetCore.Mvc.Testing` 10.0.0, xUnit 2.9.3, Python 3 with pytest 9.1.1 and PyYAML 6.0.3, Bicep CLI current in the container.

## Deploy and run (needs the lab Azure subscription)

Runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```bash
az group create -n rg-mglab-deep-dive-10 -l westeurope
az deployment group create -g rg-mglab-deep-dive-10 -n main -f infra/main.bicep --query properties.outputs -o json > outputs.json
az aks get-credentials -g rg-mglab-deep-dive-10 -n aks-mgl10
az acr build -r <acr> -t finance-worker:1 src/FinanceReview.Worker
# give the KEDA operator its identity (Learn: annotate the service account, restart the operator), then:
python3 scripts/render_manifests.py --outputs outputs.json --image <acr>.azurecr.io/finance-worker:1 --out build/
kubectl apply -f build/
python3 scripts/send_burst.py --namespace <sb name> --count 60 --poison 2
```

## What we learned / gotchas

- **Dapr extension default is high availability.** Learn: with no configuration the extension installs with `ha.enabled: true`
  and `replicaCount: 3` for each control plane service. The Bicep sets `global.ha.enabled` to `false` for a two-node lab. Not a production choice.
- **Free tier is for experiments.** Learn: the Free control plane has no cost, limited resources and is "not advised for production". Nodes are always billed.
  Learn's reliability guidance also recommends two nodes in a system pool, which the lab keeps.
- **KEDA add-on and workload identity** (Learn tutorial): create a federated credential for `system:serviceaccount:kube-system:keda-operator`,
  annotate that service account with the identity's client ID, **restart the operator**, then create a `TriggerAuthentication` with
  `podIdentity.provider: azure-workload` and `identityId`, in the same namespace as the `ScaledObject`. The tutorial grants
  *Azure Service Bus Data Owner* on the namespace, so the Bicep does too. Whether a narrower role is enough for a topic subscription
  was not verified.
- **KEDA's `namespace` is the namespace name**, not `x.servicebus.windows.net` (Learn's tutorial and KEDA's scaler page). Dapr's `namespaceName`
  is the opposite: a fully qualified domain name. One test checks that the two describe the same namespace. KEDA's scaler "is not in charge of
  managing entities": the subscription must already exist. A queue is `queueName`; a topic needs `topicName` and `subscriptionName`.
- **Dapr and the subscription name.** `consumerID` defaults to the app ID (Dapr docs), and it is the subscription name on the topic. KEDA
  must watch the same subscription, so the component sets `consumerID: finance-review` explicitly and `disableEntityManagement: "true"`
  (Dapr: otherwise Dapr creates subscriptions itself; `lockDurationInSec` and `maxDeliveryCount` then apply only when Dapr creates it,
  so those settings live in the Bicep).
- **Raw payload because the publisher is not Dapr.** Dapr docs: with `rawPayload` the sidecar still wraps the message in a CloudEvent,
  base64-encoded, and you give up CloudEvent features (tracing, deduplication per `messageId`, content-type metadata). So the app should not rely on
  the broker's `MessageId` for idempotency the way episode 7's worker does (whether it reaches the app in raw mode was not verified). This episode does **not** add an idempotency store: a real
  finance sink must upsert by `purchaseRequestId` (or use Dapr's state API). The code says so in `Sinks.cs`.
- **Statuses.** Dapr docs: a 2xx with `{"status":"SUCCESS"}` completes, `RETRY` retries, `DROP` logs a warning and drops, an unknown
  status is retried, a 404 drops, any other code retries. A poison message therefore answers 200 + `DROP` (not 400, which would retry forever).
  The Service Bus `maxDeliveryCount` (5) still dead-letters messages that keep returning `RETRY`.
- **Programmatic subscriptions are read once at startup** (Dapr docs), so a change to `/dapr/subscribe` needs a pod restart.
- **The sidecar's content type.** The worker reads the request body itself, because the Dapr sidecar delivers CloudEvents (I
  believe with `Content-Type: application/cloudevents+json`) and minimal-API body binding of `JsonElement` refuses that type. This is why
  a test posts with that header. I could not find the header or the `data_base64` field name on the Dapr pages I read, so the app accepts the
  body in `data_base64` (the CloudEvents field) or `data`, and the first deployment will show which one arrives.
- **Zero replicas is not zero nodes.** The two nodes keep running and keep costing. Scaling nodes is the cluster autoscaler's job and is not
  configured here.
- **Small Dapr buffer on purpose.** Dapr's `maxActiveMessages` defaults to 1000 messages processing or buffered per replica. With scale-out from
  zero, the first replica could take the whole burst while later replicas idle, so the component uses 10 (and 5 concurrent handlers) and a test keeps it within
  twice KEDA's `messageCount`. This is my design reasoning, not a documented rule: watch the per-pod log counts in the demo.
- **Strict readOnlyRootFilesystem** needs a writable `/tmp` for .NET, so the Deployment mounts an `emptyDir` there (not verified on the cluster).
- **Bicep:** the AKS resource uses `sku: { name: 'Base', tier: 'Free' }` (compiles and lints clean); the Dapr extension is a child `scope: aks`
  resource of type `microsoft.dapr` with its own system identity (shape from Learn's Dapr Bicep sample). Resource provider
  `Microsoft.KubernetesConfiguration` must be registered (Learn).
- **Not verified in the lab yet (needs subscription):** the deployment itself and its duration; `Standard_D2s_v5` availability and that two nodes hold Dapr,
  KEDA and up to ten 50 m pods; that the Dapr sidecar authenticates to Service Bus with the pod's workload identity (the Learn Dapr quickstart uses the same pod label and
  annotated service account, but its component uses a Redis key, so this exact path is untested; fallback: set `azureClientId` in the component);
  that the `$Default` rule override leaves a single correlation rule (same note as episode 7); that KEDA scales on a topic subscription with the Learn role;
  that `az acr build` is allowed for the subscription; real scale-out numbers (how many replicas 60 messages at 1.5 s each really produce).

## References

- [KEDA add-on for AKS](https://learn.microsoft.com/azure/aks/keda-about) · [Securely scale with the KEDA add-on and workload identity (tutorial)](https://learn.microsoft.com/azure/aks/keda-workload-identity) · [KEDA: Azure Service Bus scaler](https://keda.sh/docs/2.17/scalers/azure-service-bus/)
- [Dapr extension for AKS](https://learn.microsoft.com/azure/aks/dapr) · [Configure the extension (HA default, settings)](https://learn.microsoft.com/azure/aks/dapr-settings) · [Quickstart with workload identity](https://learn.microsoft.com/azure/aks/quickstart-dapr)
- [Dapr: Azure Service Bus topics component](https://docs.dapr.io/reference/components-reference/supported-pubsub/setup-azure-servicebus-topics/) · [Subscription methods](https://docs.dapr.io/developing-applications/building-blocks/pubsub/subscription-methods/) · [Raw payloads](https://docs.dapr.io/developing-applications/building-blocks/pubsub/pubsub-raw/) · [Pub/sub API: expected subscriber response](https://docs.dapr.io/reference/api/pubsub_api/)
- [AKS pricing tiers: Free, Standard, Premium](https://learn.microsoft.com/azure/aks/free-standard-pricing-tiers) · [Cost basics](https://learn.microsoft.com/azure/architecture/aws-professional/eks-to-aks/cost-management#aks-cost-basics) · [Quotas and limits (Free tier)](https://learn.microsoft.com/azure/aks/quotas-skus-regions) · [System node pool guidance](https://learn.microsoft.com/azure/aks/best-practices-app-cluster-reliability)
- [Bicep: Microsoft.KubernetesConfiguration/extensions](https://learn.microsoft.com/azure/templates/microsoft.kubernetesconfiguration/extensions) · [Built-in roles: Service Bus Data Receiver / Data Owner](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/integration) · [AcrPull](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/containers)
- Episode 7 (the topic and subscription this worker drains): [`../07-enterprise-api-management-apim-service-bus`](../07-enterprise-api-management-apim-service-bus)
- Blog: [Cloud-Native Application Platform: Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-04-20-cloud-native-application-platform-aks-dapr-keda-azure-service-bus/)
