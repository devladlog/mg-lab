# Demo shot list — DEVLADLOG AI #11 (conversational AI and chatbots)

Everything in `src/` and `infra/` is tested locally (74 pytest tests, Bicep build + lint) against a local stand-in for
the HTTP API. The five `screen` scenes **need the lab subscription**: every answer on screen is a real Azure OpenAI
call. No M365 tenant objects are used. The recording shows what the service really returned; if the evaluation prints
FAIL, or the window mode remembers the name, that is the episode.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-11`, region **Sweden Central** |
| Azure OpenAI | `mglab-bot-aoai-…`, kind `OpenAI`, S0, custom subdomain, keys off (Bicep) |
| Deployment (Bicep) | `chat` = **gpt-4.1-mini 2025-04-14, Standard**, capacity 50 (thousand tokens per minute), NoAutoUpgrade |
| Roles (Bicep) | `labadmin`: **Cognitive Services OpenAI User** on the account (inference only) |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI; browser on the lab tenant for the Foundry / Azure portal |

**Estimated cost for the recording window:** cents. Standard deployments are pay-per-use with no hosting fee. The
whole demo is roughly 30 chat calls (three `chat` runs) plus about 70 for `evaluate` (7 dialogues × 2 memory modes,
10 turns in the longest, plus summary calls), plus retakes. Rates come from https://aka.ms/oai/pricing, which I could
not check without a subscription, so no price is embedded. Expected total: well under €1. Delete the resource group the
same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **Quota** for gpt-4.1-mini **Standard** in Sweden Central in this subscription (Learn lists it as available in that
   region). If capacity 50 is refused, lower `chatCapacity`.
2. **Entra token on the v1 route.** `make_client` calls `/openai/v1/chat/completions` with the
   `https://ai.azure.com/.default` token (same as episode 10). If a 401 appears, wait ~5 minutes after the role
   assignment and check the role.
3. **Streaming with tools and usage.** The request sends `stream=True`, `stream_options.include_usage`, `tools`,
   `max_completion_tokens` and `temperature=0` together. Run `chat --script data/dialog-ticket.txt` once off camera; if a
   parameter is rejected the error names it. If the final usage chunk never shows up, `prompt_tokens` prints 0 and the
   estimate-error column says "n/a": report that rather than hide it.
4. **What the model does with the four slots.** Whether it asks one item at a time, whether it picks `high` for "I can't
   work at all", and whether it quotes the ticket id are model behaviour. `ticket-slots` may fail on a real run; that is a
   valid take. Do not tune the system prompt, the dialogues or the checks to get a green table.
5. **Folding.** With `--history-budget 450` the memory dialogue should start folding around turn five or six (the status
   line says so). If it never folds (the answers were short), lower the budget (for example 300) and say so in the voice
   over. Do not edit the dialogue.
6. **Window mode.** It may still "remember" the name (the model could infer it, or the name may fall inside the kept
   turns). Show whatever happens. The evaluation reports window mode as informational and never fails the gate for it.
7. **Portuguese.** The first answer in `dialog-pessoa.txt` should be Portuguese; the system message asks for the
   employee's language but nothing enforces it. If it answers in English, say so.

## Setup (off camera)

```bash
cd series/ai/episodes/11-conversational-ai-chatbots
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 74 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-11 -l swedencentral
az deployment group create -g rg-mglab-ai-11 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai11-outputs.json   # don't show this file on camera
export HELPBOT_ENDPOINT=$(jq -r .aoaiEndpoint.value /tmp/ai11-outputs.json)
export PYTHONPATH=src
```

Wait ~5 minutes for the role assignment. Dry run off camera: `python -m helpbot chat --script data/dialog-ticket.txt`.
Delete `build/sessions` before each take (`rm -rf build`), otherwise a stale session id may be reused.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user or host name). The user lines come from files in
`data/` (the script echoes them as `you>` lines), so the typing is identical on every take and the answers are the
model's.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `ticket-screen` | `screens/ticket.jpg` | `python -m helpbot chat --script data/dialog-ticket.txt`: three `you>` lines, the streamed `bot>` answers with their status lines, the final `ticket INC-…` line. |
| `deployments-screen` | `screens/deployments.jpg` | Foundry → **Models + endpoints** (or Azure portal → the resource → Deployments): `chat`, gpt-4.1-mini, Standard. Then the authentication view showing local (key) authentication disabled. Mask the resource-name suffix. |
| `handoff-screen` | `screens/handoff.jpg` | `python -m helpbot chat --script data/dialog-pessoa.txt`: the Portuguese answer (`calls=1`), then the handoff text with `calls=0`, `state=handoff` and the note `handoff by rule`. |
| `memory-screen` | `screens/memory.jpg` | `python -m helpbot chat --history-budget 450 --script data/dialog-memory.txt`: the `folded` notes, the answer to "what is my name?", the `summary:` line. Then once with `--memory window`, last answer only. |
| `evaluate-screen` | `screens/evaluate.jpg` | `python -m helpbot evaluate ; echo exit=$?`: the table, problem lines if any, the RESULT line, the exit code. About two minutes of calls; cut the wait. |

After recording, update the TODO comments in `script.yaml` with what the service returned, including any failed
scenario. Keep `build/` until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). Don't `echo`
  `$HELPBOT_ENDPOINT`; don't show `/tmp/ai11-outputs.json`.
- All dialogues are scripted and fictional (Alex Demo, Riley Demo, `alex.demo@contoso.com`, Contoso Connect). Do not type
  or read out any real name or address in a live take.
- `build/sessions/*.json` contain the whole conversation: don't open them on camera if a take used anything real.
- Don't show the pricing page or Cost Management with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-11 --yes
az cognitiveservices account purge -g rg-mglab-ai-11 -n <aoaiName> -l swedencentral
rm -rf /tmp/ai11-outputs.json build; deactivate; rm -rf .venv
```

Deleting the resource group removes the account and the deployment. Confirm in Cost Management the next day that
nothing in `rg-mglab-ai-11` is still billing.
