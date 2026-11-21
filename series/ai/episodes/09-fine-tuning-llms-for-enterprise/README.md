# DEVLADLOG AI #9 — Fine-tuning LLMs for the enterprise: the HR bot's triage, trained, gated and priced

Episodes 6 and 8 left the HR bot's triage step (`category`, `urgency`, `needs_human`) running on a `gpt-5-mini`
reasoning model with a long prompt. This episode asks the honest question: **would a small model, fine-tuned on
Contoso's own labelled messages, do the same job with a one-sentence prompt?** It builds the whole loop on **Azure
OpenAI supervised fine-tuning** (SFT, Managed Training) with `gpt-4.1-mini`, and treats every step as something that
can fail: bad data, leakage, overfitting, a model that is cheaper but worse, a hosting bill nobody planned.

```
data/labelled.jsonl (150 HR messages, EN + PT, labelled by house rules)          data/golden_ep08.jsonl (16, from episode 8)
        │ split (stratified, seeded)                                                      │
        ├─ 100 train ─┐                                                                   │ never trained on
        ├─  21 validation ─┤ preflight: format, one system prompt, duplicates,            │
        └─  29 test ───────┘ PII, leakage vs test + golden, tokens, cost  ──► training.jsonl / validation.jsonl (UTF-8, BOM)
                                                                                     │ files + job (Standard training, Sweden Central)
                                                                                     ▼
              base gpt-4.1-mini + LONG prompt (~670 tokens)  ◄── same 45 held-out items ──►  fine-tuned + SHORT prompt (~35 tokens)
                                        └──────── evaluate: accuracy + 95% intervals + sign test + gates ────────┘
                                                                  exit 0 = promote · exit 1 = don't
```

| Question | Answer in this episode |
|---|---|
| Is the data fit to train on? | `validate.py`: chat format, one system message, valid answers, duplicates, conflicting labels, personal data, size, leakage |
| Can I afford it? | `economics.py`: training = tokens × epochs × price (Learn's formula) and the break-even against the long prompt, **with hosting**; prices are arguments, never guessed |
| Did it work? | `evaluate.py`: both models on the same held-out items; category, urgency, `needs_human` (and its recall), format errors, input tokens, latency |
| Is the difference real? | Wilson 95% intervals and an exact sign test: with 45 items, "97% vs 93%" is usually noise, and the report says so |
| May it ship? | Four gates: valid JSON ≥ 98%, category not worse than the baseline, `needs_human` recall ≥ 90%, ≥ 50% fewer input tokens |
| Where does it run? | Training type **Standard** (the job runs in the resource's region, so the data stays in Sweden Central), deployment **Developer** for the test (no hosting fee, 24 hours) |

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Azure OpenAI account (Sweden Central, keys off, custom subdomain), `base` = gpt-4.1-mini 2025-04-14 pinned, **Cognitive Services OpenAI Contributor** for the developer |
| [`data/labelled.jsonl`](data/labelled.jsonl) | 150 fictional HR messages (about 61 % English, 39 % Portuguese) with category, urgency, needs_human, written to Contoso's house rules |
| [`data/golden_ep08.jsonl`](data/golden_ep08.jsonl) | Episode 8's 16-question golden set, copied unchanged: extra test data and a leakage target |
| [`src/fttriage/prompts.py`](src/fttriage/prompts.py) | `SHORT_SYSTEM` (trained in) and `baseline_system()` (instructions + 9 house rules + 8 worked examples) |
| [`src/fttriage/dataset.py`](src/fttriage/dataset.py) | Loading, stratified split, `to_chat()`, JSONL writer (UTF-8 with BOM) |
| [`src/fttriage/validate.py`](src/fttriage/validate.py) | Pre-flight checks; errors block the upload |
| [`src/fttriage/tokens.py`](src/fttriage/tokens.py), [`economics.py`](src/fttriage/economics.py) | Token counts (`o200k_base`), training cost, serving cost, break-even calls per month |
| [`src/fttriage/jobs.py`](src/fttriage/jobs.py) | Upload, create the SFT job on the v1 endpoint (`trainingType`, `method.supervised.hyperparameters`), wait, metrics, overfitting signal |
| [`src/fttriage/deploy.py`](src/fttriage/deploy.py) | Deploy / delete the fine-tuned model with the management REST API (Developer SKU by default) |
| [`src/fttriage/evaluate.py`](src/fttriage/evaluate.py) | Run both models, metrics, intervals, sign test, gates, report |
| [`src/fttriage/cli.py`](src/fttriage/cli.py) | `python -m fttriage prepare / submit / deploy / evaluate / cleanup / cost` |
| [`tests/`](tests) | 58 pytest tests |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q            # 58 passed (the two Bicep tests are skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
PYTHONPATH=src python -m fttriage prepare --out build --price-per-million <rate from the pricing page>
```

`prepare` on the repo data prints: `100 train / 21 validation / 29 test + 16 golden`, about **7,100 training tokens**
(a system prompt of 34 tokens in every example), the baseline prompt at **672 tokens** against **34** for the short
one, and `PREFLIGHT OK`. At 3 epochs that is about 21,000 billable training tokens: cents, not euros, at any published
rate. **The model is the cost to watch, not the training.**

What the tests cover (the "models" are lookup tables over the labelled data, **not** language models: they prove the
plumbing, metrics and gates, not model quality):
- `test_dataset.py`: 150 examples, all 7 categories, both languages; stratified, disjoint, deterministic split;
  **no training example is an exact or near copy of a validation, test or golden item**; the baseline prompt's
  worked examples aren't in the test data; BOM and real UTF-8 (Portuguese diacritics, not `\u` escapes).
- `test_validate.py`: every pre-flight rule triggers on a crafted bad file (fewer than 10 examples, wrong roles,
  invalid answers, two system messages, duplicates, the same message labelled twice, e-mail / IBAN / phone / tax
  number / card number, leakage, 70,000-word example, encoding) and numbers like "25th of April" don't.
- `test_jobs.py`: the **real `openai` SDK** against a local stub of the v1 endpoint: Entra bearer token with scope
  `https://ai.azure.com/.default`, `purpose=fine-tune`, the job body (model, files, suffix, seed, `trainingType`,
  `method.supervised.hyperparameters`), queued → running → succeeded without resubmitting, a failed job raising the
  service's message, a timeout that says the job keeps running, `results.csv` parsing, the overfitting signal.
- `test_deploy.py`: PUT body and URL exactly as Learn's example (`api-version=2025-07-01-preview`, SKU, model, version
  `"1"`), polling `provisioningState`, a base-model name refused before any request, delete, management token scope.
- `test_evaluate.py`: the right system prompt reaches each model, billed `usage` is what's measured, malformed JSON
  and failed calls count as wrong, a tuned model that is cheaper **but worse** is not promoted, one that matches
  accuracy but **never escalates a sensitive message** is not promoted either.
- `test_cli_and_bicep.py`: `prepare` end to end, exit 1 on personal data in training, `cost`, `cleanup` (deployment first, then the uploaded files), and the compiled Bicep
  (keyless, pinned base deployment, only the OpenAI Contributor role).

Tested with Python 3.13, `openai 3.57.0`, `tiktoken 0.14.0`, `azure-identity 1.27.0`, `requests 2.34.2`, Bicep CLI
0.49.2.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-09 -l swedencentral
az deployment group create -g rg-mglab-ai-09 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export AOAI=<aoaiEndpoint>
cd src   # or: export PYTHONPATH=src
python -m fttriage prepare --out ../build --price-per-million <training rate>
python -m fttriage submit  --endpoint $AOAI --out ../build            # Standard training; a queued job is normal
python -m fttriage deploy  --subscription <id> --resource-group rg-mglab-ai-09 --account <aoaiName> --out ../build
python -m fttriage evaluate --endpoint $AOAI --out ../build ; echo $?  # 0 = promote, 1 = don't
python -m fttriage cleanup --subscription <id> --resource-group rg-mglab-ai-09 --account <aoaiName> --endpoint $AOAI --out ../build
az group delete -n rg-mglab-ai-09 --yes
```

Needs the lab subscription: the job, the deployment and the evaluation are real service calls. Nothing in this folder
claims a result the service hasn't produced: the numbers on screen come from the run recorded in `demo.md`.

## What we learned / gotchas

- **Fine-tuning is not the first move.** Learn: benefits aren't guaranteed, it adds training and hosting costs, and
  it doesn't replace retrieval for current information. Here it's justified by a stable task with clear labels, a
  long prompt paid on every call, and data we own. Policies that change weekly belong in retrieval (episode 3).
- **The system message must match.** Learn: the system message used at inference must be the same one used in
  training, or results differ. `SHORT_SYSTEM` is in every training example and `evaluate` sends it unchanged;
  `validate` refuses a file with two different system messages.
- **The labels are the product.** The house rules (expense claims are payroll, a home-office chair is equipment, a
  hybrid-allowance question is benefits) are Contoso conventions. A base model can only know them if you tell it,
  on every call. That is the whole case for tuning here, and it only holds if the labels are consistent: the
  validator blocks one message with two labels.
- **Keep test data out of training, mechanically.** Learn's overview lists "evaluation leakage" first among the
  challenges. We check exact and near duplicates (Jaccard ≥ 0.8) of every training example against validation, test and
  episode 8's golden set, and the baseline prompt's worked examples against the test data, so neither model is graded
  on what it was shown.
- **Personal data does not belong in a training file.** Learn says to inspect for sensitive information before
  uploading. The validator looks for e-mail addresses, IBANs, phone numbers, long digit runs (tax numbers) and card
  numbers; it's a safety net, not a classifier, and the real answer is to build the dataset from anonymised text.
- **`processed` is not "valid".** Learn's troubleshooting for premium healthcare models notes that a file reaches
  `processed` after upload and scanning only; schema validation happens at job preprocessing. Validate locally first.
- **Training type decides where the data goes.** `Standard` trains in the resource's region (data residency), `Global`
  is cheaper but copies data and weights to another region, `Developer` uses idle capacity with no guarantees, and
  Learn says the **data zone** training type is currently US only. For a Portuguese company that leaves Standard in
  Sweden Central. We send `trainingType` explicitly; per Learn, leaving it out means Standard. We only expose the two
  API values Learn documents (`Standard`, `GlobalStandard`).
- **Hosting is a running meter.** A deployed fine-tuned model on Standard or Global Standard has an hourly hosting fee
  whether or not you call it; deployments idle for more than 15 days are deleted (the model remains). **Developer**
  deployments have no hosting fee but live 24 hours, have no SLA and no data-residency guarantee, and are for
  evaluation only. Learn also says Developer deployments aren't supported for `gpt-4o-mini`; they are for `gpt-4.1-mini`.
- **You can't delete a fine-tuned model that is still deployed**, and cancelling training doesn't delete deployments or
  stop their charges (Learn): `cleanup` removes the deployment first.
- **The Developer SKU has three spellings on Learn** (`developertier` in the REST sample, `Developer` in the CLI sample,
  `DeveloperTier` in the deployment types table). We send `DeveloperTier`; `--sku` and `deploy.SKUS` are the one place
  to change it if the service disagrees (see demo.md "needs verification").
- **Quota is separate.** Learn (premium healthcare fine-tuning troubleshooting) says base and fine-tuned deployments
  use separate quota pools per model and a fine-tuned deploy can fail with `InsufficientQuota`; check the model's
  fine-tune quota before the recording.
- **45 items can't separate two good models.** A single wrong answer moves accuracy by about two points; the Wilson
  interval for 42/45 correct runs from roughly 82 % to 98 %. That is why the report prints intervals and a sign test,
  and why the gate is "not worse" rather than "better". More labelled data is the fix, and it's the most valuable thing
  you can spend a weekend on.
- **Loss isn't the goal.** Learn: compare checkpoints on held-out tasks, not training loss; rising validation loss
  while training loss falls means look at the failures, then fewer epochs or a smaller learning-rate multiplier.
  `overfit_signal()` flags exactly that.
- **Fine-tunes expire with their base model.** Learn lists maintenance as a challenge: reassess when task data changes
  or the base model approaches retirement. The model version is pinned in Bicep (`NoAutoUpgrade`) and episode 8's monitor
  is what tells you when to retrain.
- **BOM.** Learn's classic how-to says training files are UTF-8 and include a byte-order mark. We write one and read
  both ways; the current Foundry how-to doesn't mention it. Don't hand-edit these files in a tool that strips it.

## References

- [Training in Microsoft Foundry (fine-tuning overview): methods, training types, deployment types, supported models, challenges](https://learn.microsoft.com/azure/foundry/fine-tuning/overview)
- [Fine-tune a model with supervised fine-tuning in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/openai/how-to/fine-tuning) — Python / REST job, hyperparameters, metrics
- [Customize a model with fine-tuning (classic)](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/fine-tuning) — data format, BOM, 10 minimum / 50 to start, same system message, deployment clean-up
- [Manage fine-tuning costs in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/fine-tuning/cost-management) — SFT price formula, hosting fee
- [Deploy a fine-tuned model for testing (Developer deployment)](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/fine-tune-test) — REST deploy sample, 24-hour lifetime
- [Deployment types for Foundry Models](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/deployment-types) — SKU codes
- [Deploy fine-tuned models in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/fine-tuning/deploy-fine-tuned-models)
- [Azure OpenAI v1 API](https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle#code-changes) — `/openai/v1/`, Entra token provider scope
- [Azure built-in roles: AI + machine learning](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#cognitive-services-openai-contributor) — Cognitive Services OpenAI Contributor
- [Troubleshooting for Azure OpenAI fine-tuning](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/fine-tuning-troubleshoot) and [premium healthcare fine-tuning troubleshooting table](https://learn.microsoft.com/azure/foundry/how-to/healthcare-ai/fine-tune-premium-healthcare-models#evaluate-the-fine-tuned-model) — `processed` vs schema validation, quota, `trainingType`
- [Region availability: Standard deployments](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability#standard-regional) — gpt-4.1-mini in Sweden Central
- Pricing is read from [aka.ms/oai/pricing](https://aka.ms/oai/pricing) at recording time and never stored in this repo
- Blog: [Fine-Tuning LLMs for Enterprise — Complete Guide](https://www.devladlog.com/articles/ai/2026-04-01-fine-tuning-llms-complete-guide-2026/)
