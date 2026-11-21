# Demo shot list — DEVLADLOG AI #5 (AI agents and orchestration)

Everything in `src/` and `infra/` is tested locally (27 pytest tests, Bicep build + lint). The three `screen` scenes
**need the lab subscription**: they show the real agent calling the real `gpt-5-mini` deployment.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner) — €30/month budget alert already set |
| Resource group | `rg-mglab-ai-05`, region **Sweden Central** |
| Azure OpenAI | `Microsoft.CognitiveServices/accounts`, kind `OpenAI`, SKU **S0**, custom subdomain, key auth disabled. No fixed cost. |
| Model deployment | `chat` = **gpt-5-mini 2025-08-07**, deployment type **DataZoneStandard**, capacity 20 (= 20K tokens per minute), version pinned |
| Role | Cognitive Services OpenAI User for `labadmin` on the account (assigned by the Bicep) |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell with Python 3.10+), Azure CLI, Bicep CLI |
| Lab users / M365 | Not needed. No tenant objects are created. |

**Estimated cost for the recording window:** pay per token only. One `apagent.run` is roughly 8 to 12 model calls of a
few thousand tokens each; one `apagent.pipeline` run is 3 calls. Warm-up plus three or four takes stay in the low
hundreds of thousands of tokens: expected well under €1 at the published gpt-5-mini Data Zone rates (check the
Azure OpenAI pricing page in EUR before recording). Delete the resource group the same day.

**Needs verification before deploying:** gpt-5-mini 2025-08-07 with DataZoneStandard quota in Sweden Central for the
lab subscription (Foundry portal → Quotas). If there is no Data Zone quota, use `chatSku='GlobalStandard'` and say so
in the README (data may then be processed in any Azure region).

## Setup (off camera)

```bash
cd series/ai/episodes/05-ai-agents-orchestration
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                       # expect 27 passed
az login                                                        # labadmin, off camera
az group create -n rg-mglab-ai-05 -l swedencentral
az deployment group create -g rg-mglab-ai-05 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai05-outputs.json   # don't show this file on camera
export AOAI=$(jq -r .aoaiEndpoint.value /tmp/ai05-outputs.json)
unset OPENAI_API_KEY                                            # keeps the generic client on Azure
```

Wait ~5 minutes for the role assignment. Warm-up (off camera):
`PYTHONPATH=src python -m apagent.run --endpoint $AOAI --deployment chat --approve none` must end with the
`=== Queue after the run ===` table. A `401`/`403` means the role hasn't propagated or the endpoint isn't the
custom-subdomain one. Then `rm -rf audit outbox` so the recorded runs start clean (each run reloads
`data/invoices.json`, so the queue always starts in its original state).

Terminal: dark theme, font ≥ 16 pt, window 1920×1080, prompt shortened (no user/host name).

## Screens to capture

Record in this order: `approval` and `result` are the same take.

| Scene id | File | What must be on screen |
|---|---|---|
| `approval` | `screens/approval.jpg` | `PYTHONPATH=src python -m apagent.run --endpoint $AOAI --deployment chat --audit audit/run.jsonl`. Capture the moment the run pauses: `>>> APPROVAL NEEDED  approve_invoice` with `invoice_id:` and `note:` lines and the cursor after `Approve? [y/N]`. Then type `y`. If the agent asks a second approval (for an invoice the policy forbids), answer `y` too: the store will refuse it, and that's worth showing. |
| `result` | `screens/result.jpg` | Same terminal after the run: `=== Agent ===` (one line per invoice), `=== Tool calls (audit) ===` (tool, outcome, ms, arguments; a `refused` row if a forbidden approval was tried), `=== Queue after the run ===` (one `approved`, others `review`/`rejected`), the tokens line. Scroll so all three blocks fit. |
| `pipeline-run` | `screens/pipeline.jpg` | `PYTHONPATH=src python -m apagent.pipeline INV-2026-0142 --endpoint $AOAI --deployment chat`: `=== checker ===` (INVOICE / ISSUE / POLICY / ACTION), `=== writer ===` starting with `Subject:`, and `saved outbox/INV-2026-0142-draft.md (draft, not sent)`. |

After recording, update the TODO comments in `script.yaml`:
- `approval`: which invoice the agent proposed (expected `INV-2026-0088`, the faded scan whose total a person
  confirms). If it proposed nothing, re-run once; if it still doesn't, record that honestly and adjust the narration.
- `result`: whether a second approval was attempted and refused (`refused` in the audit table).
- `pipeline-run`: that the checker quoted 1000.00 + 230.00 vs 1240.00.
- Optional: keep `audit/run.jsonl` from the recorded run as evidence (fictional data only), outside the repo.

## Masking

- Mask the Azure OpenAI resource name/endpoint if it appears (`mglab-agent-aoai-…openai.azure.com`), the
  subscription name/ID and the signed-in user (`pipeline/mask.js` for any portal page). Use `$AOAI`; don't `echo` it
  and don't show `/tmp/ai05-outputs.json`.
- Invoice data (Northwind, Adventure Works, Litware, Fabrikam, VAT numbers `PT 000 000 …`, amounts) is fictional
  and can stay on screen. `approved_by` shows "AP clerk" (the CLI default), not a real person.

## Tear-down

```bash
az group delete -n rg-mglab-ai-05 --yes
# Cognitive Services accounts are soft-deleted; purge to release the name and stop any lingering billing objects:
az cognitiveservices account purge -g rg-mglab-ai-05 -n $(jq -r .aoaiName.value /tmp/ai05-outputs.json) -l swedencentral
rm -rf audit outbox /tmp/ai05-outputs.json; deactivate; rm -rf .venv
```
