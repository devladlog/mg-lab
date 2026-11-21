# Demo shot list: DEVLADLOG Deep Dive #10, Cloud-native application platform (AKS + Dapr + KEDA + Service Bus)

Code, test and Bicep/YAML scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs the Azure subscription.** Offline (container): 21 xUnit tests and 31 pytest tests pass, `bicep build` and
`bicep lint` are clean, the worker was published and called with `curl`. **Not yet run against Azure:** the Bicep deployment,
the image build, the Dapr sidecar, KEDA scaling, `send_burst.py`. Record each outcome in the README ("Not verified" lists
what to check) and fix the narration if reality differs (especially the replica counts in `scale-screen`).

## Lab environment

Recorded on the **lab Windows laptop** (host): Windows Terminal with PowerShell 7 (Azure CLI, kubectl, Python), Edge for the Azure
portal. No Hyper-V VM and no Power Platform environment are needed. No Microsoft 365 licences are involved; the only account used is `labadmin`
(Owner on the lab subscription).

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-10`, West Europe)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| AKS `aks-mgl10` control plane | **Free** tier (Learn: no control plane cost; not for production) | free |
| AKS node pool, 2 x `Standard_D2s_v5` | Linux VMs, system pool | billed per node-hour: check the [VM pricing page](https://azure.microsoft.com/pricing/details/virtual-machines/linux/); keep the cluster up for the recording only. Two nodes are what Learn recommends for a system pool |
| Service Bus namespace, topic `purchase-events`, subscription `finance-review` | **Standard** (topics + duplicate detection), Entra only | base charge per Azure subscription that has a Standard namespace plus operations: check the [pricing page](https://azure.microsoft.com/pricing/details/service-bus/); delete the group the same day |
| Container Registry `acrmgl10<token>` | **Basic**, admin user off | small daily charge: [pricing page](https://azure.microsoft.com/pricing/details/container-registry/) |
| 2 user-assigned identities, 2 federated credentials | n/a | free |
| Dapr extension, KEDA add-on | n/a | no extra charge; they run on the nodes above |

AKS also creates a node resource group `MC_...` (VM scale set, load balancer, disks); deleting the main group removes it. Budget alert
`mglab-monthly` (EUR 30) stays active. No Log Analytics, no Container Insights, no Defender plans, no public ingress (nothing is exposed; you work with `kubectl`).

**Local tools on the laptop:** Azure CLI with the `k8s-extension` extension (`az extension add -n k8s-extension`), `kubectl`
(`az aks install-cli`), Python 3.10+, .NET SDK 10 and Bicep CLI for the test run, the repo checked out.

## Setup (off camera)

1. **Tests first**
   ```powershell
   cd series/deep-dive/episodes/10-cloud-native-application-platform-aks-dapr-keda-
   dotnet test tests/FinanceReview.Tests -m:1        # expect Passed: 21
   python -m pytest tests/contracts -q               # expect 31 passed
   ```
2. **Providers and size check**
   ```powershell
   az login                                                           # off camera
   az provider register --namespace Microsoft.KubernetesConfiguration  # Learn: needed for cluster extensions (Dapr)
   az provider register --namespace Microsoft.ContainerService
   az vm list-skus -l westeurope --size Standard_D2s_v5 -o table      # pick another size and pass -p nodeVmSize=... if restricted
   ```
3. **Deploy**
   ```powershell
   az group create -n rg-mglab-deep-dive-10 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-10 -n main -f infra/main.bicep --query properties.outputs -o json > outputs.json   # not on camera
   $o = (Get-Content outputs.json | ConvertFrom-Json)
   az aks get-credentials -g rg-mglab-deep-dive-10 -n $o.aksName.value --overwrite-existing
   kubectl get nodes
   ```
   **Check and write into the README:** (a) the deployment succeeds, with the time it took; (b) the Dapr extension is *Succeeded*
   (`az k8s-extension show --cluster-type managedClusters -c aks-mgl10 -g rg-mglab-deep-dive-10 -n dapr`); (c) `az aks show --query "[workloadAutoScalerProfile, securityProfile, oidcIssuerProfile]"`
   shows KEDA and workload identity enabled; (d) `kubectl get pods -n dapr-system` shows one pod per control plane service (no HA).
4. **Image** (cloud build, no local Docker)
   ```powershell
   az acr build -r $o.acrName.value -t finance-worker:1 src/FinanceReview.Worker
   ```
   If ACR Tasks is not available for the subscription, say so in the README and build and push from a machine with Docker.
5. **KEDA operator identity** (Learn tutorial; the Bicep created the federated credential and the role, these two steps are in the cluster)
   ```powershell
   kubectl annotate serviceaccount keda-operator azure.workload.identity/client-id=$($o.kedaClientId.value) -n kube-system
   kubectl rollout restart deploy keda-operator -n kube-system
   kubectl describe pod -n kube-system -l app.kubernetes.io/name=keda-operator | Select-String AZURE_      # expect AZURE_CLIENT_ID, AZURE_FEDERATED_TOKEN_FILE ...
   ```
6. **Sender role for the recording account** (Owner does not include data-plane rights)
   ```powershell
   $me = az ad signed-in-user show --query id -o tsv
   $topic = az servicebus topic show -g rg-mglab-deep-dive-10 --namespace-name $o.serviceBusNamespace.value -n purchase-events --query id -o tsv
   az role assignment create --role "Azure Service Bus Data Sender" --assignee-object-id $me --assignee-principal-type User --scope $topic
   ```
   Role assignments can take a few minutes to apply (same as episode 7).
7. **Manifests**
   ```powershell
   python scripts/render_manifests.py --outputs outputs.json --image "$($o.acrLoginServer.value)/finance-worker:1" --out build
   kubectl apply -f build/
   kubectl get pods -n contoso-finance -w       # the Deployment starts at 1 replica, KEDA then scales it to 0 after the cooldown (120 s)
   ```
   **Check and write into the README:** (a) the pod has two containers (`worker`, `daprd`) and both are Ready; (b) the `daprd` log shows the subscription
   to `purchase-events` established (no authentication error: if there is one, set `azureClientId` in `deploy/10-dapr-component.yaml` to `appClientId` and re-apply); (c) `kubectl describe scaledobject -n contoso-finance finance-worker`
   shows `Ready` and no `KEDAScalerFailed` authentication error (a 401 or 403 means the KEDA role); (d) a manual `send_burst.py --count 3` is processed.
8. **Dry run** the whole sequence once, including the scale-in to zero (about two minutes after the last message plus the polling interval).
   Count the replicas you actually get from 60 messages and note it in the README.

## Screens to capture (1920x1080, browser zoom 100 %, terminal font large)

| Scene id | File | What must be on screen |
|---|---|---|
| `deploy-screen` | `screens/platform.jpg` | Terminal: `az aks show --query "[workloadAutoScalerProfile, securityProfile, oidcIssuerProfile]"`, `kubectl get pods -n dapr-system`, `kubectl get pods -n kube-system -l app=keda-operator`, `kubectl get component,scaledobject,deploy -n contoso-finance`. Issuer URL, subscription id, tenant id masked |
| `idle-screen` | `screens/idle.jpg` | Left: `kubectl get scaledobject,deploy,pods -n contoso-finance` with 0 pods; right: portal Service Bus > purchase-events > Subscriptions > finance-review, active message count 0 |
| `scale-screen` | `screens/scale-out.jpg` | `python scripts/send_burst.py --namespace <ns> --count 60 --poison 2` + `kubectl get pods -n contoso-finance -w` + portal active count falling. Second take two minutes after the last message: pods Terminating back to 0 |
| `logs-screen` | `screens/logs.jpg` | `kubectl logs -n contoso-finance -l app=finance-worker -c worker --tail=40`: "Finance review opened for PR-90xx" lines and two `Delivery DROP` warnings; then the portal showing active 0 and dead-letter 0 on finance-review |

Order: platform, idle, burst and scale-out (with the logs captured right after), scale-in to zero.

## Masking

Run `pipeline/mask.js` before portal captures. Mask subscription id, tenant id, the Service Bus namespace and registry names, the AKS OIDC issuer URL,
identity client ids and any object ids. No token or kubeconfig content is ever shown (`az aks get-credentials` output stays off camera).

## Tear-down

```powershell
az group delete -n rg-mglab-deep-dive-10 --yes
kubectl config delete-context aks-mgl10 ; kubectl config delete-cluster aks-mgl10    # remove the stale local entries
Remove-Item outputs.json, build -Recurse -ErrorAction SilentlyContinue
```

Everything is in the one group (and the AKS-managed `MC_...` group, which AKS removes with it): cluster, nodes, registry, Service Bus, identities,
role assignments. Confirm in the portal that both resource groups are gone. No Entra objects, licences or tenant settings are created in this episode.
