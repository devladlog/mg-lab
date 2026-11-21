# DEVLADLOG AI #14 — MLOps and ML pipelines: train, gate, register, roll out

Blog guide: [MLOps and ML Pipelines: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-05-07-mlops-pipelines-complete-guide-2025/)

Episodes 8 and 9 watched and fine-tuned *language* models. The Contoso Porto service desk also wants a classic ML model: **at
ticket creation, the probability that the ticket will breach its SLA**, so the desk can staff and route. This episode builds the
release process around it on **Azure Machine Learning** (CLI v2 YAML, MLflow, managed online endpoints): a pipeline that validates, trains and
**gates**; a registry that stores the evidence with each version; a blue-green rollout; and a CI workflow with OpenID Connect.
The ticket data is **fictional and generated from a rule we wrote**, so the episode is about the process, not the accuracy.

```
raw tickets ──► prepare (validate schema/values/label rate, split BY TIME) ──► train (HistGradientBoosting, MLflow model + signature)
                       │ exit 2: nothing downstream runs                                  │
                                                                                          ▼
                              evaluate (pyfunc, newer tickets): AUC floor · not worse than production · P1-slice recall
                                       │ exit 3 = gate says no = the pipeline job FAILS
                                       ▼ job Completed
 scripts/train-and-register.sh ─► az ml model create (tags: test_auc, pipeline_job) ─► scripts/deploy-canary.sh: other colour, 0 % ─► smoke request ─► 10 %
        ▲ production AUC read from the registry tag of the latest version                                            scripts/promote.sh: 100 %, delete old
```

| Question | Answer in this episode |
|---|---|
| How is the pipeline defined? | `aml/pipeline.yml` + three command components (`aml/components/*.yml`); every step uses `src/` as its code and one conda environment on `cpu-cluster` (min nodes 0, as Learn advises, to avoid idle charges) |
| What stops bad data? | `prepare.validate`: columns, values, dates, minimum rows, label rate in a sane band. Exit 2, every problem listed. The `missing-column` scenario shows it |
| Why a time split? | The test set is newer than the training set (tested), the way the model will be used |
| What is the gate? | `gate.py`, a pure function: AUC ≥ 0.70, not more than 0.02 below production, recall on **P1** breaches ≥ 0.60 at threshold 0.5. **All our numbers.** `evaluate` exits 3 on "no", so the job fails |
| Where is "production"? | A tag (`test_auc`) on the latest registered model. The script reads it, passes it as `baseline_auc`, and writes it on the next registration |
| What is registered? | An **MLflow model** from the pipeline job output, with `test_auc` and `pipeline_job` tags. The model's signature (6 inputs, probability out) is what Azure ML turns into the endpoint contract |
| How is it served? | Managed online endpoint, `auth_mode: aad_token`, no scoring script and no environment file (Learn: no-code deployment for MLflow models) |
| How does it roll out? | Learn's blue-green: new colour with no traffic, a request straight to it (`--deployment-name`), 90/10, then `promote.sh` |
| What does CI do? | `ci/mlops.yml`: tests on pull requests; on manual dispatch, sign in with OIDC (`azure/login@v2`, `id-token: write`), generate data, run the scripts. **Structure checked in tests, not executed** |

| Path | What it is |
|---|---|
| [`src/slabreach/`](src/slabreach) | `data.py` (fictional history, scenarios `baseline`, `noisy`, `missing-column`), `prepare.py`, `train.py`, `gate.py`, `evaluate.py`, `serving.py` (a request through the model like the endpoint does), `cli.py` |
| [`aml/`](aml) | `pipeline.yml`, `components/{prepare,train,evaluate}.yml`, `environment/conda.yml`, `endpoint.yml`, `deployment.yml`, `sample-request.json` |
| [`scripts/`](scripts) | `train-and-register.sh`, `deploy-canary.sh`, `promote.sh` (Azure CLI with the `ml` extension) |
| [`ci/mlops.yml`](ci/mlops.yml) | GitHub Actions workflow (copy to `.github/workflows/`) |
| [`infra/main.bicep`](infra/main.bicep) | Workspace (system-assigned identity), storage, key vault, Application Insights on Log Analytics, `cpu-cluster` scaling to zero; optional AzureML Data Scientist for a CI identity |
| [`tests/`](tests) | 37 pytest tests |

Tested with Python 3.13, `scikit-learn 1.9.1`, `pandas 3.0.5`, `mlflow-skinny 3.18.0`, `azure-ai-ml 1.35.2`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
MLFLOW_ALLOW_FILE_STORE=true python -m pytest tests -q            # 37 passed (about 1.5 minutes)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
PYTHONPATH=src python -m slabreach generate --out build/raw        # tickets.csv, 6000 fictional rows
```

What the tests cover (everything below runs for real on this machine, except the cloud itself):
- `test_data_prepare_gate.py`: the generator is deterministic and has the contract; validation lists every problem; the split is by time with no overlap;
  the missing-column extract is refused and writes nothing; the gate as a function (floor, relative drop, slice, all reasons).
- `test_train_evaluate_serving.py`: a real run of generate, prepare, train, evaluate: promoted, MLflow model with signature and probability output, metrics and
  params logged, reproducible, learned something sensible (P1 network ticket riskier than a P4 access ticket); a noisy extract is rejected with exit 3;
  `aml/sample-request.json` is parsed and scored the way the endpoint does; a request without `input_data` is refused.
- `test_aml_files_and_scripts.py`: every YAML is loaded by the **Azure ML SDK's offline schema validation** (a deliberately wrong pipeline fails it); the three
  **component commands written in the YAML are executed** in order with the paths substituted; the workflow has OIDC and no stored credentials; the three shell scripts run
  against a **stand-in `az`** that records its arguments (first run registers with the AUC tag, the production AUC becomes `baseline_auc`, a failed job or a "do not promote" decision registers nothing,
  first deployment is blue with all traffic, later ones go to the other colour with a smoke request before 90/10, promote then deletes); the compiled Bicep.

Expected local numbers, for orientation only (seed 1 / seed 2 / noisy seed 4, 1,200 test tickets): test AUC 0.775 / 0.765 / 0.680; recall on P1 breaches at 0.5: 0.83 / 0.89 / 0.73.

## Deploy and run (needs a subscription; see `demo.md`)

```bash
az extension add --name ml --yes
az group create -n rg-mglab-ai-14 -l westeurope
az deployment group create -g rg-mglab-ai-14 -f infra/main.bicep -p infra/main.bicepparam --query properties.outputs
export RG=rg-mglab-ai-14 WS=<workspaceName> ENDPOINT_NAME=<unique name>
PYTHONPATH=src python -m slabreach generate --out build/raw --seed 1
scripts/train-and-register.sh                 # first run: no production model, registers version 1
PYTHONPATH=src python -m slabreach generate --out build/raw --scenario noisy --seed 4
scripts/train-and-register.sh                 # the gate says no: job Failed, nothing registered
PYTHONPATH=src python -m slabreach generate --out build/raw --seed 2
scripts/train-and-register.sh                 # version 2
scripts/deploy-canary.sh 1 && scripts/deploy-canary.sh 2     # blue = v1, green = v2 at 10 %
az ml online-endpoint invoke -n $ENDPOINT_NAME --request-file aml/sample-request.json -g $RG -w $WS
```

Needs the lab subscription: the pipeline jobs, the registry, the endpoint. Nothing in this folder claims a result the cloud has not produced.

## What we learned / gotchas

- **A gate that fails the job is simple and crude.** `evaluate` exits 3, the step and the job fail, and the script never registers. It is easy to reason about; it is also
  indistinguishable, in the job list, from a crash (the logs say which). Learn's pipeline docs describe `command` and `sweep` job types in a pipeline; we did not use conditional steps.
- **Thresholds are ours.** On this fictional data seeds 1 to 3 gave test AUCs of 0.775, 0.765 and 0.742 on 1,200 tickets. A relative tolerance of 0.005 would have rejected
  noise, so the code uses 0.02 and says why. On real history, derive the tolerance from repeated runs.
- **Judge slices, not only the average.** The P1 recall check exists because an average can hide the group the model was built for.
- **MLflow 3 changed things Learn's samples rely on.** Learn's custom `score.py` imports `infer_and_parse_json_input` from `mlflow.pyfunc.scoring_server`; the installed MLflow 3.18
  does not have it (the equivalent is `infer_and_parse_data` on a `dataframe_split` dict), so `serving.py` tries both. MLflow 3 also refuses a plain `./mlruns` file store unless
  `MLFLOW_ALLOW_FILE_STORE=true` (tests only; Azure ML sets its own tracking URI), and its default scikit-learn serialization needs `skops`; we pin `cloudpickle`, which MLflow warns can execute code
  on load. For a no-code deployment Azure ML's own server parses the request, so `serving.py` is a local approximation.
- **Pipeline-level inputs are plain values.** Our first `pipeline.yml` declared `baseline_auc` as `{type: number, default: 0}` and the SDK's offline validation rejected it; literal inputs are written `baseline_auc: 0`
  (component inputs do take `type`/`default`/`min`/`max`). This is why the tests load every YAML.
- **No local test for no-code MLflow endpoints.** Learn: testing no-code MLflow deployments with local endpoints isn't currently supported. Hence the smoke request to the new colour in the cloud.
- **Cost lives in compute.** Learn: set a cluster's minimum nodes to 0; a managed online endpoint uses VMs for its deployments; a failed deployment that got as far as creating compute can still incur charges, so delete it.
  Learn's blue-green example uses one instance and advises at least three for high availability; we use one for a recording. Prices are not embedded (not checked without a subscription); the quota for the VM family is not checked either.
- **Delete the workspace permanently.** Learn: deleting a workspace is a soft delete by default (14 days), you can't reuse its name until it expires or you delete it permanently, and deleting the workspace does not delete its storage, key vault, Application Insights
  or container registry. `demo.md` uses `az ml workspace delete --all-resources --permanently-delete`, then deletes the resource group.
- **The workflow is not run here.** It follows Learn's OIDC pattern (`permissions: id-token: write`, `azure/login@v2` with client, tenant and subscription IDs from secrets, `actions/checkout@v4`), the tests parse it,
  but running it needs an Entra app or managed identity with a federated credential for the repository.
- **Azure CLI details to confirm on the day** (not verifiable without a subscription): registering from `azureml://jobs/<job>/outputs/model` for a *pipeline* output, `az ml model show --label latest`, `--set tags.x=y` on `az ml model create`,
  and where `az ml job download --output-name` puts the file (the script searches for `decision.json`).

Out of scope on purpose: AutoML, feature stores, the Python SDK pipeline authoring (`dsl`), scheduled retraining, data-drift monitors (episode 8 covers drift for the HR bot), batch endpoints, Kubernetes endpoints,
conditional pipeline steps, and Azure ML registries for cross-workspace promotion.

## References

- [Create and run component-based ML pipelines with the CLI](https://learn.microsoft.com/azure/machine-learning/how-to-create-component-pipelines-cli) — pipeline and component YAML, serverless compute, registering components
- [Deploy MLflow models to online endpoints](https://learn.microsoft.com/azure/machine-learning/how-to-deploy-mlflow-models-online-endpoints) — no-code deployment, register from a job output, `input_data` request format, local-endpoint limitation
- [Perform safe rollout of new deployments](https://learn.microsoft.com/azure/machine-learning/how-to-safely-rollout-online-endpoints) — blue-green, `--traffic "blue=90 green=10"`, `--deployment-name`, deleting a deployment
- [Use GitHub Actions with Azure Machine Learning](https://learn.microsoft.com/azure/machine-learning/how-to-github-actions-machine-learning) — OIDC sign-in, secrets, workflow shape
- [Create an Azure Machine Learning compute cluster](https://learn.microsoft.com/azure/machine-learning/how-to-create-attach-compute-cluster) and [Plan to manage costs](https://learn.microsoft.com/azure/machine-learning/concept-plan-manage-cost)
- [Recover workspace data while soft deleted](https://learn.microsoft.com/azure/machine-learning/concept-soft-delete) and [az ml workspace delete](https://learn.microsoft.com/cli/azure/ml/workspace)
- [Azure built-in roles for AI + machine learning](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning) — AzureML Data Scientist
- Azure quickstart template for the workspace and its dependencies: `Azure/azure-quickstart-templates`, `quickstarts/microsoft.machinelearningservices/machine-learning-workspace`
- Blog: [MLOps and ML Pipelines: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-05-07-mlops-pipelines-complete-guide-2025/)
