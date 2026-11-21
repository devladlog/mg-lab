# Demo shot list — DEVLADLOG AI #15 (Generative AI and LLMs)

Everything in `src/` and `infra/` is tested locally (57 pytest tests, Bicep build + lint) against a local stand-in server
that exists **only for the automated tests**. The five `screen` scenes are recorded against a **real Azure OpenAI deployment**
in the lab subscription; no M365 tenant objects are used. The tokens scene (code scene, real offline output) needs no Azure.
Show what the service really returned: if temperature zero is not repeatable, or a question stays uncertain with the
handbook, that is the episode. Do not tune data, prompts or thresholds to get a nicer table.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-15`, region **Sweden Central** |
| Azure OpenAI | `mglab-gen-aoai-…`, kind `OpenAI`, S0, custom subdomain, keys off (Bicep) |
| Deployment (Bicep) | `chat` = **gpt-4.1-mini 2025-04-14, Standard**, capacity 50 (thousand tokens per minute), NoAutoUpgrade. A non-reasoning model on purpose |
| Role (Bicep) | `labadmin`: **Cognitive Services OpenAI User** on the account (inference only) |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI; browser on the lab tenant for the Foundry / Azure portal capture |

**Estimated cost for the recording window:** cents. Standard deployments are pay-per-use, no hosting fee. The full run is about
8 probe calls, 32 sampling calls (about 400-token prompts, short answers), 6 streaming/blocking calls and 2 budget calls, i.e.
roughly 50 calls and a few tens of thousands of tokens. Unit prices come from https://aka.ms/oai/pricing, which I could not
check without a subscription; I did not embed any price. Delete the resource group the same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **Quota and availability** of gpt-4.1-mini as Standard in Sweden Central for this subscription (Learn's region table listed it on 21 Nov 2026). If not, pick another region from that table and change `-l` and the `location` parameter.
2. **Parameters accepted by the deployment on the v1 route with an Entra token:** `logprobs` + `top_logprobs=5`, `temperature`, `seed`, `max_completion_tokens`, `stream_options.include_usage`. If one is rejected the error names it; change `probe.request_args` / `sampling.run_setting` / `stream.stream_once` and the matching test.
3. **What the first token looks like.** `probe` asks for "the letter only" and normalises `C`, ` C`, `c`, `C)`. If the model answers in another form (for example `Option C`), the first token will be something else and the table will say so; show that and adjust the prompt in `probe.SYSTEM` rather than the data.
4. **Whether temperature 0 is repeatable here.** Unknown until it runs. Either answer is the content of the `sample-screen` scene.
5. **Whether the fingerprint is returned.** The `fingerprints` column prints `-` if `system_fingerprint` is absent; say so on camera if so.
6. **Why a stream may start slowly.** Default streaming is buffered for the content filter; the first-content time includes that. Do not claim a number before the run.

## Setup (off camera)

```bash
cd series/ai/episodes/15-generative-ai-llms
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 57 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-15 -l swedencentral
az deployment group create -g rg-mglab-ai-15 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai15-outputs.json   # don't show this file on camera
export LLMPROBE_ENDPOINT=$(jq -r .aoaiEndpoint.value /tmp/ai15-outputs.json)
export PYTHONPATH=src
```

Wait ~5 minutes for the role assignment. Quick check (off camera): `python -m llmprobe budget --context-budget 400` should print an answer.
Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user/host name). In the script the `$AOAI` placeholder stands for the
endpoint environment variable: on camera just run the command (the variable is already exported; do not echo it).

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `tokens` (code scene, no capture) | — | Optional b-roll: `python -m llmprobe tokens` and `python -m llmprobe tokens --show "Quantos dias de férias tenho?"` (the pieces of one Portuguese sentence). Output is deterministic; the numbers in `script.yaml` and README are real. |
| `deployment` | `screens/deployment.jpg` | Foundry → **Models + endpoints** (or Azure portal → the resource → Deployments): `chat`, gpt-4.1-mini 2025-04-14, Standard. Then the resource's authentication view showing local (key) authentication disabled. Mask the resource-name suffix. |
| `probe-screen` | `screens/probe.jpg` | `python -m llmprobe probe`: 8 table rows (4 cases × without/with context), then the candidate lines. Pause on the `capital` control and on one policy question with and without context. |
| `sample-screen` | `screens/sample.jpg` | `python -m llmprobe sample --runs 8 ; echo exit=$?`: four rows, any `FAIL` lines, the exit code. About a minute of calls; cut the wait. Optional second take with `--show` to read two different wordings side by side. |
| `stream-screen` | `screens/stream.jpg` | `python -m llmprobe stream --runs 3`: the summary lines and the `first run: N chunks in total, M with text` line. |
| `budget-screen` | `screens/budget.jpg` | `python -m llmprobe budget --context-budget 120` (Carry-over dropped, read what the model answers), then `--context-budget 400` (kept). Show the estimated vs billed prompt tokens in both. |

After recording, update the TODO comments in `script.yaml` with what the service returned.
Keep `build/` and `/tmp/ai15-outputs.json` out of the capture; delete them after publishing.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). Don't `echo` `$LLMPROBE_ENDPOINT`; don't show `/tmp/ai15-outputs.json`.
- The handbook, the questions and the Portuguese sentences are fictional (Contoso, Porto office). Don't show the pricing page or Cost Management with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-15 --yes
az cognitiveservices account purge -g rg-mglab-ai-15 -n <aoaiName> -l swedencentral
rm -f /tmp/ai15-outputs.json; deactivate; rm -rf .venv
```

Deleting the resource group removes the account and its deployment. Confirm in Cost Management the next day that nothing in
`rg-mglab-ai-15` is still billing.
