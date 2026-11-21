# Demo shot list — DEVLADLOG AI #9 (fine-tuning LLMs for the enterprise)

Everything in `src/` and `infra/` is tested locally (58 pytest tests, Bicep build + lint) against local doubles. The
four `screen` scenes **need the lab subscription**: a real fine-tuning job, a real deployment, real model calls. No M365
tenant objects are used. The recording shows what the service really did; if the evaluation says DO NOT PROMOTE, that
is the episode.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-09`, region **Sweden Central** |
| Azure OpenAI | `mglab-ft-aoai-…`, kind `OpenAI`, S0, custom subdomain, keys off. Deployment `base` = **gpt-4.1-mini 2025-04-14, Standard**, capacity 50, NoAutoUpgrade (Bicep) |
| Fine-tuning job | base model `gpt-4.1-mini-2025-04-14`, supervised, **training type Standard** (stays in the region), ~7,100 training tokens × auto epochs |
| Fine-tuned deployment | `triage-ft`, **Developer** deployment type (no hosting fee, 24-hour life), capacity 50, created by `python -m fttriage deploy` |
| Roles (Bicep) | `labadmin`: **Cognitive Services OpenAI Contributor** on the account (fine-tuning, deployments, inference). Subscription Owner covers the ARM deployment call |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI; browser on the lab tenant for the Foundry / Azure portal |

**Estimated cost for the recording window:** training ≈ 21,000 billable tokens (7,100 × 3 epochs if the service picks
3; `prepare` prints the number) × the Standard training rate of gpt-4.1-mini from https://aka.ms/oai/pricing (Learn:
price = tokens × epochs × rate; queue time, failed jobs and safety checks are not billed). Evaluation: 45 items on the
base model with a ~670-token prompt (≈ 30K input tokens) plus 45 on the tuned model with a ~35-token prompt, per-token.
The Developer deployment has no hourly hosting fee (Learn); **don't use Standard for the recording** (it bills hosting
by the hour). Expected total: well under €1. Delete the resource group the same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **gpt-4.1-mini Standard fine-tuning quota in Sweden Central**, and that `trainingType: "Standard"` is accepted with an
   Entra token on the v1 endpoint for this resource. Fallback if Standard is unavailable: `--training-type GlobalStandard`
   (cheaper, **no data residency**: say so on camera, and change the "stays in Sweden Central" sentence in the `job` scene).
2. **Developer SKU spelling.** Learn writes it `developertier` (REST sample), `Developer` (CLI sample) and `DeveloperTier`
   (deployment types table). `deploy` sends `DeveloperTier`. If the PUT is rejected, try `--sku` with another spelling
   by editing `deploy.SKUS` (the tests pin the current one), or deploy once from the portal and keep the name `triage-ft`.
3. **Fine-tuned deployment quota.** Learn (premium healthcare troubleshooting) says fine-tuned deployments draw on a
   separate `-finetune` quota pool per model; check **Management center > Quota** for gpt-4.1-mini in Sweden Central
   before starting, otherwise `InsufficientQuota`.
4. **`response_format`/`temperature=0` on the fine-tuned deployment.** The evaluation uses temperature 0 and plain text
   (no structured outputs). If the deployment rejects `max_completion_tokens`, switch `evaluate.run` to `max_tokens`.
5. **How long Standard training queues.** Plan for minutes to hours; see the schedule below.

## Setup (off camera)

```bash
cd series/ai/episodes/09-fine-tuning-llms-for-enterprise
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 58 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-09 -l swedencentral
az deployment group create -g rg-mglab-ai-09 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai09-outputs.json   # don't show this file on camera
export AOAI=$(jq -r .aoaiEndpoint.value /tmp/ai09-outputs.json)
export ACCOUNT=$(jq -r .aoaiName.value /tmp/ai09-outputs.json)
export SUB=$(az account show --query id -o tsv)
export PYTHONPATH=src
```

Wait ~5 minutes for the role assignment. Check the base deployment answers (off camera):
`python -c "from fttriage import jobs; c=jobs.make_client('$AOAI'); print(c.chat.completions.create(model='base', messages=[{'role':'user','content':'ping'}], max_completion_tokens=5).choices[0].message.content)"`.

### Schedule (so the recording is a real run, not a replay)
1. **T-3 h (off camera):** `python -m fttriage prepare --out build` then `python -m fttriage submit --endpoint $AOAI --out build`.
   It waits and writes `build/job.json` when the job finishes. A queued job is normal; do not resubmit. If it fails, the
   error message is printed (read it, fix the data, don't loosen the validator).
2. **T-1 h:** when `submit` has printed `fine-tuned model: …`, run `python -m fttriage deploy --subscription $SUB
   --resource-group rg-mglab-ai-09 --account $ACCOUNT --out build`. A Developer deployment **expires after 24 hours**, so
   deploy on the day you record.
3. **Recording:** the four captures below, in order. The job and the deployment are the real ones created in steps 1–2.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user/host name). The comparison table needs ~90 columns.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `preflight-run` | `screens/prepare.jpg` | `python -m fttriage prepare --out build --price-per-million <rate>` (read the rate from the pricing page beforehand; don't show the page). The split line (100 / 21 / 29 + 16 golden), the languages line, the tokens line (baseline vs short prompt), the cost estimate, `PREFLIGHT OK`. Run it fresh on camera; it takes a few seconds. |
| `job-screen` | `screens/job.jpg` | Foundry portal → the resource → **Fine-tuning**, open the finished job: status Succeeded, base model, training type Standard, metrics (training loss, full validation loss and accuracy). Also the terminal line `fine-tuned model: …ft-…` from `submit` (mask the id suffix) and, if shown, the overfitting line or "no overfitting signal". |
| `deployment-screen` | `screens/deployments.jpg` | Foundry → **Models + endpoints** (or Azure portal → the OpenAI resource → Deployments): `base` (gpt-4.1-mini, Standard) and `triage-ft` (fine-tuned, **Developer**, Succeeded). |
| `evaluate-run` | `screens/evaluate.jpg` | `python -m fttriage evaluate --endpoint $AOAI --out build ; echo exit=$?`. The full table, the sign-test line, the four gate lines, `PROMOTE` / `DO NOT PROMOTE`, the exit code. About a minute of model calls; cut the wait. |

After recording, update the TODO comments in `script.yaml` with the real numbers and verdict. **Do not edit the
dataset, the thresholds or the prompts to make the result look better**; if the tuned model failed a gate, the honest
narration says which one and the screen stays. Keep `build/` (training.jsonl, validation.jsonl, test.jsonl, job.json)
until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user, the resource-name suffix and the fine-tuned model id suffix
  (`pipeline/mask.js`). Don't `echo` `$AOAI`, `$SUB`, `$ACCOUNT`; don't show `/tmp/ai09-outputs.json`.
- The 150 messages are fictional; no personal data is in any file (the preflight blocks it).
- Don't show the pricing page or the Cost Management blade with real amounts.

## Tear-down

```bash
python -m fttriage cleanup --subscription $SUB --resource-group rg-mglab-ai-09 --account $ACCOUNT --endpoint $AOAI --out build
# a Developer deployment also removes itself after 24 hours; the fine-tuned model must not be deployed to be deleted
az group delete -n rg-mglab-ai-09 --yes
az cognitiveservices account purge -g rg-mglab-ai-09 -n $ACCOUNT -l swedencentral
rm -rf /tmp/ai09-outputs.json build; deactivate; rm -rf .venv
```

`cleanup` deletes the `triage-ft` deployment and then the uploaded training, validation and result files. Deleting the
resource group removes the account, the base deployment and the fine-tuned model with it. Confirm in Cost Management
the next day that nothing in `rg-mglab-ai-09` is still billing.
