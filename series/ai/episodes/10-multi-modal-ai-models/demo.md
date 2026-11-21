# Demo shot list — DEVLADLOG AI #10 (multi-modal AI models)

Everything in `src/` and `infra/` is tested locally (43 pytest tests, Bicep build + lint) against local doubles. The four
`screen` scenes **need the lab subscription**: real vision, Whisper and text-to-speech calls. No M365 tenant objects are
used. The recording shows what the service really returned; if the evaluation prints "do not ship", that is the episode.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-10`, region **Sweden Central** |
| Azure OpenAI | `mglab-mm-aoai-…`, kind `OpenAI`, S0, custom subdomain, keys off (Bicep) |
| Deployments (Bicep) | `vision` = **gpt-4.1-mini 2025-04-14, Standard**, capacity 50; `whisper` = **whisper 001, Standard**, capacity 3; `tts` = **tts 001, Standard**, capacity 3. All NoAutoUpgrade |
| Roles (Bicep) | `labadmin`: **Cognitive Services OpenAI User** on the account (inference only; no deployment or fine-tuning rights) |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI, an image viewer; browser on the lab tenant for the Foundry / Azure portal |

**Estimated cost for the recording window:** a few cents. Standard deployments are pay-per-use with no hosting fee.
The run makes 5 short TTS calls, 5 Whisper calls (a few seconds of audio each), then 7 cases × 2 detail settings = 14
vision calls (plus any retakes). Rates and units come from https://aka.ms/oai/pricing, which I could not check without a
subscription; I did not embed any price. Expected total: well under €1. Delete the resource group the same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **Quota and availability** of gpt-4.1-mini, `whisper` and `tts` as **Standard in Sweden Central** for this subscription
   (Learn's region table listed them when this was written). If `tts` is unavailable, use West Europe or `tts-hd` and
   change `--tts`; the voice notes can also be recorded by a person. Whisper is allowed to read real speech here only if
   it is your own voice, never a colleague's.
2. **Entra token on the v1 audio routes.** `python -m mmticket voice` and `transcribe` call `/openai/v1/audio/speech` and
   `/openai/v1/audio/transcriptions` with the `https://ai.azure.com/.default` token and the deployment name as `model`.
   Run both once off camera. If a 401 appears, check the role (allow ~5 minutes) and the token scope.
3. **Whisper parameters.** `response_format=json`, `language` and `prompt` are sent; confirm the deployment accepts them.
4. **Vision call parameters.** `response_format` with a strict `json_schema` together with image input, `temperature=0`
   and `max_completion_tokens` on gpt-4.1-mini; and that the service honours `detail` (low / high). If a parameter is
   rejected, the error says which; change `ticket.extract` and keep the test in step.
5. **How Whisper writes spoken codes.** "CX-4102" may come back as `CX-4102`, `CX 4102` or `C X 4102` (all handled) or
   `CX four one oh two` (not handled: the guard won't see a code, and the conflict case could pass the guard).
   Whatever it writes, show it; adjust the narration TODO in the `conflict-screen` scene.
6. **Whether low detail reads the small-font case.** Unknown until it runs. Either answer is the honest content of the
   `evaluate-screen` scene. Do not tune the pictures, the thresholds or the prompt to get a nicer table.
7. **Portuguese TTS quality** of the `tts` model for `access-pt` (pronunciation of "ID-5501"). If it is unusable, say so
   and replace that one voice note with your own recording (`build/audio/access-pt.mp3`).

## Setup (off camera)

```bash
cd series/ai/episodes/10-multi-modal-ai-models
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 43 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-10 -l swedencentral
az deployment group create -g rg-mglab-ai-10 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai10-outputs.json   # don't show this file on camera
export MMTICKET_ENDPOINT=$(jq -r .aoaiEndpoint.value /tmp/ai10-outputs.json)
export PYTHONPATH=src
python -m mmticket samples --out build/images
python -m mmticket voice --out build/audio                       # 5 synthetic voice notes; listen to each once
```

Wait ~5 minutes for the role assignment. Quick check (off camera): `python -m mmticket transcribe build/audio/vpn-clean.mp3`
should print the sentence with the code.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user/host name). Open `build/images/vpn-clean.png` in
an image viewer for the `ticket-screen` intro.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `ticket-screen` | `screens/ticket.jpg` | The clean screenshot for two seconds, then `python -m mmticket ticket --image build/images/vpn-clean.png --audio build/audio/vpn-clean.mp3 --detail high`: the image line, the ticket JSON, an empty `flags`, the `usage:` line. |
| `deployments-screen` | `screens/deployments.jpg` | Foundry → **Models + endpoints** (or Azure portal → the resource → Deployments): `vision`, `whisper`, `tts`, all Standard. Then the resource's authentication view showing local (key) authentication disabled. Mask the resource-name suffix. |
| `conflict-screen` | `screens/conflict.jpg` | `python -m mmticket ticket --image build/images/vpn-conflict.png --audio build/audio/vpn-conflict.mp3`: `needs_human: true` and the `conflict:` flag. Show the transcript if useful (`transcribe` on the same file). |
| `evaluate-screen` | `screens/evaluate.jpg` | `python -m mmticket evaluate --images build/images --audio-dir build/audio ; echo exit=$?`: the transcript-source lines, the low and high rows, gate reasons if any, the RESULT line, the exit code. About a minute of calls; cut the wait. |

After recording, update the TODO comments in `script.yaml` with what the service returned, including a failed gate.
Keep `build/` until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). Don't `echo`
  `$MMTICKET_ENDPOINT`; don't show `/tmp/ai10-outputs.json`.
- All screenshots are drawn by `samples.py`; the products (Contoso Connect, Mail, Print, Sync, Acesso), printers and
  error codes are fictional. The voices are synthetic: say so in the narration or on screen.
- Don't show the pricing page or Cost Management with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-10 --yes
az cognitiveservices account purge -g rg-mglab-ai-10 -n <aoaiName> -l swedencentral
rm -rf /tmp/ai10-outputs.json build; deactivate; rm -rf .venv
```

Deleting the resource group removes the account and all three deployments. Confirm in Cost Management the next day that
nothing in `rg-mglab-ai-10` is still billing.
