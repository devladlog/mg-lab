# Demo shot list — DEVLADLOG AI #14 (MLOps and ML pipelines)

Everything in `src/`, `aml/`, `scripts/`, `ci/` and `infra/` is tested locally (37 pytest tests, Bicep build + lint): the data, the three
steps, the MLflow model and the request format run for real; the YAML is validated by the Azure ML SDK; the scripts run against a stand-in `az`.
The four `screen` scenes **need the lab subscription**: every result on screen comes from the real Azure Machine Learning workspace, cluster, registry and
endpoint. No M365 tenant objects are used. The recording shows what the cloud really returned; a rejected model or a failed job is the episode, not a retake.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-14`, region **West Europe** |
| Azure ML workspace | `mglab-mlops-mlw-…` (Bicep), system-assigned identity, with its storage account, key vault, Application Insights and Log Analytics workspace. No container registry in Bicep (Azure ML is expected to create one when the first environment is built; if it does, it is in the same resource group) |
| Compute cluster | `cpu-cluster`, `Standard_DS3_v2`, min 0 / max 1 node, idle scale-down 2 minutes (Bicep) |
| Managed online endpoint | created by `scripts/deploy-canary.sh`: `auth_mode: aad_token`, deployments `blue` and `green`, `Standard_DS3_v2`, 1 instance each |
| Roles | `labadmin` is Owner on the subscription: no assignment needed. The CI identity is not created (the workflow is shown, not run) |
| Recording machine | Lab Windows laptop: Windows Terminal with WSL (bash, Python 3.10+, `pandas`, `numpy`; the scripts need `bash` and `python3`), Azure CLI with the `ml` extension; browser on the lab tenant for Azure ML studio |

**Estimated cost for the recording window:** a workspace has no charge of its own (Learn: it is a control-plane resource; its dependencies, compute and endpoints can bill). Billable items here are:
cluster nodes while a job runs (scale to zero after 2 idle minutes), the Log Analytics ingestion (tiny), and, the important one, **two endpoint VMs (`blue` + `green`) for as long as they exist**. Plan the endpoint part in one sitting of well under two hours and
delete it at once. Prices are on the Azure pricing pages, which could not be checked without a subscription, so no amounts are quoted. Learn also warns that a failed deployment can incur charges: delete failed deployments.

**Needs verification before recording (not checkable without a subscription):**
1. **VM quota.** `Standard_DS3_v2` is 4 vCPU. The cluster (max 1 node) plus two endpoint deployments needs 12 vCPU of the DSv2 family in West Europe. Check usage and quota (Learn: *Manage and increase quotas*) and, if short, change `trainingVmSize` and `instance_type` together (they appear in `infra/main.bicepparam` and `aml/deployment.yml`) or pick another region.
2. **Provider registration.** `Microsoft.MachineLearningServices` (and `Microsoft.ContainerRegistry`, `Microsoft.Insights`) must be registered on the subscription.
3. **Environment build.** The first job builds a Docker image from `aml/environment/conda.yml` (base image `mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest`, Python 3.12, the pinned packages). This takes minutes; if a pin cannot be resolved (for example `scikit-learn==1.9.1` on Python 3.12), the job fails at environment build: the fix is to change the pin in `conda.yml`, run the tests, and say so in the voice over.
4. **CLI behaviours** used by the scripts: `az ml model create --path azureml://jobs/<job>/outputs/model` for a pipeline job output; `az ml model show --label latest --query tags.test_auc`; `--set tags.x=y`; `az ml job download --output-name decision` (the script looks for `decision.json` anywhere under the download folder). If one differs, fix the script, re-run the tests, and tell the story honestly.
5. **No-code deployment.** The model is saved by MLflow 3.18 (pinned in the environment, so the model's own `conda.yaml` carries the same pins). If the endpoint's scoring container cannot load it, show the container log and say what the version mismatch was; it is a real MLflow-versions finding.
6. **Numbers.** Locally, seed 1 / seed 2 / noisy seed 4 gave test AUC 0.775 / 0.765 / 0.680. The cloud environment pins the same package versions, so similar values are expected; read what the evaluate step prints, not these.

## Setup (off camera)

```bash
cd series/ai/episodes/14-mlops-ml-pipelines
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
MLFLOW_ALLOW_FILE_STORE=true python -m pytest tests -q            # expect 37 passed
az login                                                          # labadmin, off camera
az extension add --name ml --yes
az group create -n rg-mglab-ai-14 -l westeurope
az deployment group create -g rg-mglab-ai-14 -f infra/main.bicep -p infra/main.bicepparam \
   --query properties.outputs -o json > /tmp/ai14-outputs.json    # don't show this file on camera
export RG=rg-mglab-ai-14 WS=$(jq -r .workspaceName.value /tmp/ai14-outputs.json)
export ENDPOINT_NAME=slabreach-$(date +%m%d)-$RANDOM              # endpoint names are unique per region
export PYTHONPATH=src
```

Dry run off camera (this also builds and caches the environment image, so the recorded run is shorter): `python -m slabreach generate --out build/raw && MODEL_NAME=sla-breach-dryrun scripts/train-and-register.sh`. The `MODEL_NAME` override keeps the dry run out of the `sla-breach` registry, so the recorded first run really starts with no production model. Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `pipeline-screen` | `screens/pipeline.jpg` | `python -m slabreach generate --out build/raw --seed 1` then `scripts/train-and-register.sh` (first run): "production AUC: 0", job name, status lines, "registered sla-breach version 1". Then studio → Jobs → the pipeline job: graph prepare → train → evaluate completed; evaluate step logs with the `PROMOTE` line. |
| `gate-screen` | `screens/gate.jpg` | `python -m slabreach generate --out build/raw --scenario noisy --seed 4`, then `scripts/train-and-register.sh`: production AUC read from the tag, "ended as Failed: nothing is registered". Studio → failed job → evaluate step logs with `REJECT` and its reasons; Models still lists only version 1. |
| `registry-screen` | `screens/registry.jpg` | After `generate --seed 2` and a third run (version 2): studio → Models → `sla-breach`: versions, open one: type MLflow, tags `test_auc`, `pipeline_job`, link to the job. |
| `endpoint-screen` | `screens/endpoint.jpg` | `scripts/deploy-canary.sh 1`, then `scripts/deploy-canary.sh 2` (output: live, new, canary 10 %); studio → Endpoints → the endpoint → Details: blue 90 / green 10, authentication Microsoft Entra token; `az ml online-endpoint invoke -n $ENDPOINT_NAME --request-file aml/sample-request.json` with two predictions. |

After recording, update the TODO comments in `script.yaml` with what the cloud returned, including the exact rejection reasons and anything that failed.
The `register-code`, `canary-code` and `gotcha` scenes show files and need no capture. Do not run or show `ci/mlops.yml` as if it had run: it has not.
Optional extra (only if time allows and a throwaway repo plus an Entra app with a federated credential exist): run it once and add a screen, then change the gotcha bullet.

## Masking

- Mask subscription ID, tenant, signed-in user, the workspace-name suffix, endpoint name suffix and scoring URI (`pipeline/mask.js`). Don't `echo` `$WS` carelessly, don't show `/tmp/ai14-outputs.json`.
- The data is generated (`python -m slabreach generate`); ticket IDs look like `T0100001`. No real tickets, names or systems appear.
- Don't show Cost Management with real amounts or the pricing pages.

## Tear-down

```bash
az ml online-endpoint delete --name $ENDPOINT_NAME --yes -g $RG -w $WS
az ml workspace delete --name $WS -g $RG --all-resources --permanently-delete --yes
az group delete -n rg-mglab-ai-14 --yes
rm -rf /tmp/ai14-outputs.json build mlruns; deactivate; rm -rf .venv
```

Why permanently: Learn says a soft-deleted workspace keeps its name for 14 days and that deleting a workspace leaves its storage, key vault, Application Insights and container registry behind; `--all-resources` and
`--permanently-delete` handle both, and the resource group delete removes whatever is left. Check the portal (Azure Machine Learning → Recently deleted) and Cost Management the next day: nothing in `rg-mglab-ai-14` should still bill.
