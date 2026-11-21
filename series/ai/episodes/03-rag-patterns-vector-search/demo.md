# Demo shot list — DEVLADLOG AI #3 (RAG patterns and vector search)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant apps | none |
| Lab user | `labadmin` (the recording account): Owner on the subscription; its object ID is passed as `developerPrincipalId` (data-plane roles on Search and Azure OpenAI) |
| Azure | Resource group **`rg-mglab-ai-03`** in **Sweden Central**, deployed by `infra/main.bicep`: Azure AI Search **Basic** (1 replica / 1 partition, billed per hour while it exists: roughly €0.10/hour, check the pricing page; semantic ranker on the free plan), one Azure OpenAI account with `embed-small` (text-embedding-3-small, Standard, 50k TPM) and `chat` (gpt-5-mini 2025-08-07, Data Zone Standard, 10k TPM): a few thousand tokens, cents. Deploy right before recording; tear-down deletes the group and purges the account |
| Licences / trials | none beyond the subscription |
| Recording machine | The Windows lab laptop: Foundry/Azure portal in the browser, bash terminal in WSL (Ubuntu) with Azure CLI, Python 3.10+ and this folder (the commands below are bash), plus `jq` in WSL |

Everything in `src/` and `infra/` is tested locally (38 pytest tests, Bicep build + lint). The four `screen` scenes
**need the lab tenant**: they show the real index, the real scorecard and real model answers.

## Prerequisites
- Lab subscription where you can create resource groups and **assign roles** (Owner or User Access Administrator
  on the resource group) — the Bicep creates role assignments.
- Resources created by `infra/main.bicep` (all deleted at the end):
  - **Azure AI Search, Basic tier**, 1 replica / 1 partition. Billed for as long as it exists: deploy right before
    recording, delete right after. Basic is needed because the Free tier has no managed identity (the vectorizer
    uses one) — see README gotchas. Semantic ranker on the **free** plan (monthly allowance; no extra charge).
  - **Azure OpenAI** account with two pay-as-you-go deployments: `embed-small` (text-embedding-3-small v1,
    `Standard`, 50k TPM) and `chat` (gpt-5-mini 2025-08-07, `DataZoneStandard`, 10k TPM). Cost of the demo is a
    few thousand tokens. Set a budget alert on the resource group.
- **Needs verification before deploying:** on Learn (*Foundry Models sold by Azure → model availability*), check
  that in the chosen region (default `swedencentral`) text-embedding-3-small is offered as **Standard** and
  gpt-5-mini 2025-08-07 as **Data Zone Standard**, and that you have the quota. If not, change `embeddingSku` /
  `chatSku` or the region in `infra/main.bicepparam` (keep both services in the same region) and note it in README.
- Also check that the region offers **semantic ranker** (Learn: *Supported regions for Azure AI Search*).
- Local: Azure CLI, Python 3.10+, Bicep CLI, this folder.

## Setup (lab tenant, off camera)
```bash
cd series/ai/episodes/03-rag-patterns-vector-search
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                       # expect 38 passed
az login                                                        # labadmin, off camera
az group create -n rg-mglab-ai-03 -l swedencentral
az deployment group create -g rg-mglab-ai-03 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/rag-outputs.json  # don't show this file on camera
export SEARCH=$(jq -r .searchEndpoint.value /tmp/rag-outputs.json)
export AOAI=$(jq -r .aoaiEndpoint.value /tmp/rag-outputs.json)
```
Role assignments can take several minutes to take effect (Learn: up to 5–10 minutes for search data roles).
Until then the search calls return 401/403. Warm-up, off camera:
```bash
PYTHONPATH=src python -m hrrag.ingest --search-endpoint $SEARCH --aoai-endpoint $AOAI   # "indexed 25 chunks into 'hr-handbook'"
PYTHONPATH=src python -m hrrag.evaluate --search-endpoint $SEARCH --mode vector         # proves the vectorizer + MI role work
```
If the vector query fails with an authentication error from the vectorizer, the search identity's
*Cognitive Services OpenAI User* assignment hasn't propagated yet: wait and retry. A dimension error means the
deployment behind `embed-small` isn't text-embedding-3-small.

## Screens to capture (1920×1080, dark terminal theme, font ≥ 16 pt)

| Scene id | File | What must be on screen |
|---|---|---|
| `indexed` | `screens/indexed.jpg` | Split screen. Left: terminal, re-run `PYTHONPATH=src python -m hrrag.ingest --search-endpoint $SEARCH --aoai-endpoint $AOAI` (it's idempotent: `mergeOrUpload`) ending with `indexed 25 chunks into 'hr-handbook'`. Right: portal → search service → **Indexes** → `hr-handbook` with the document count (25) and vector index size. Optionally the **Keys** page showing *Role-based access control* selected (API keys disabled) — never open key values. |
| `scorecard` | `screens/scorecard.jpg` | Terminal: `PYTHONPATH=src python -m hrrag.evaluate --search-endpoint $SEARCH` — the full table (keyword, vector, hybrid, hybrid_semantic: hit@1, hit@5, MRR, misses) and the out-of-scope list with reranker scores. |
| `answer` | `screens/answer.jpg` | Terminal: `PYTHONPATH=src python -m hrrag.answer "If I don't use all my vacation this year, can I keep some days?" --search-endpoint $SEARCH --aoai-endpoint $AOAI` — answer with `[n]` citations, five sources with score + reranker score, cited ones starred, `grounded=True`. |
| `not-found` | `screens/not-found.jpg` | Terminal: same command with `"What is the company car policy?"` — the fixed sentence `I can't find that in the Contoso HR handbook.`, the five unrelated sources, `not_found=True`. |

After recording:
- Fill the `TODO` in the `scorecard` narration (best mode in this run, and one question keyword missed but vector
  found — look at the `misses` column).
- Check the `answer` and `not-found` TODOs: the narration assumes `grounded=True` and `not_found=True`. If the live
  run differs, keep the honest take and adjust the narration (a wrong refusal is exactly the gotcha scene).

Optional B-roll: portal → index → **Search explorer**, a hybrid query in JSON view with
`"vectorQueries":[{"kind":"text","text":"working from abroad","fields":"content_vector"}]`.

## Masking
- Mask the search service name and endpoint (`mglab-rag-srch-…`), the Azure OpenAI account name/endpoint
  (`mglab-rag-aoai-…`), subscription name/ID, tenant name and the signed-in user in the portal header
  (`pipeline/mask.js`). The `$SEARCH`/`$AOAI` variables keep endpoints off the terminal; don't `echo` them and
  don't show `/tmp/rag-outputs.json`.
- The handbook content, Contoso, form codes and questions are fictional and can stay on screen.

## Tear-down
```bash
az group delete -n rg-mglab-ai-03 --yes
# Azure OpenAI (Cognitive Services) accounts are soft-deleted; purge so the name and quota are released:
az cognitiveservices account purge -g rg-mglab-ai-03 -n <aoai-account-name> -l swedencentral
rm /tmp/rag-outputs.json; deactivate; rm -rf .venv
```
