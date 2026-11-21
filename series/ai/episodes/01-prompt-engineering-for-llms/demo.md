# Demo shot list — DEVLADLOG AI #1, Prompt engineering for LLMs

Everything except the four `screen` scenes is already real (code excerpts and test output from this folder).
The live part needs **one Azure OpenAI deployment** in the lab subscription. Status: **needs tenant** for the
scorecard, the A02 answer and the temperature call; tests and `--dry-run` run offline.

## Prerequisites
- Lab Azure subscription with the budget alert (pay-as-you-go). Cost driver: tokens only. One evaluation run is
  20 tickets × 2 prompts = 40 small calls (the v2 request is about 3,000 characters of messages and schema per call, plus hidden reasoning tokens on the output side); check the
  [Azure OpenAI pricing page](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/) for
  gpt-5-mini before recording and expect a few cents. Don't loop the run.
- A Microsoft Foundry (Azure OpenAI) resource in a region where **gpt-5-mini 2025-08-07** is available for your
  deployment type (check *Model availability* on Learn). gpt-5-mini is GA with retirement 2027-07-13.
- Your lab user has **Cognitive Services OpenAI User** on that resource (role assignment can take up to 5 minutes).
- Local: Python 3.10+, Azure CLI, this folder.

## Setup (lab tenant)
1. Foundry portal → your resource → **Models + endpoints** → **Deploy model** → `gpt-5-mini`, version `2025-08-07`,
   deployment name **`triage-mini`**, smallest TPM that works (e.g. 10k). Keep the default guardrail (content filter).
2. Resource → **Access control (IAM)** → add **Cognitive Services OpenAI User** for the lab user.
3. Terminal:
   ```bash
   cd series/ai/episodes/01-prompt-engineering-for-llms
   python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
   python -m pytest tests -q                       # expect 37 passed
   az login                                        # lab user (browser sign-in, not on camera)
   export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
   PYTHONPATH=src python -m triage.evaluate --data data/tickets.jsonl --prompt v2 --dry-run | head -20   # sanity
   ```

## Screens to capture (1920×1080, dark terminal theme, font ≥ 16 pt)

| Scene id | File | What must be on screen |
|---|---|---|
| `deployment` | `screens/deployment.jpg` | Foundry portal, deployment details of `triage-mini`: model name `gpt-5-mini`, version `2025-08-07`, deployment type, rate limit (TPM). |
| `scorecard` | `screens/scorecard.jpg` | Terminal after `PYTHONPATH=src python -m triage.evaluate --data data/tickets.jsonl --prompt v1 --prompt v2 --deployment triage-mini --model gpt-5-mini` — the full scorecard table (both rows, all columns). |
| `attack` | `screens/attack.jpg` | Same run with `--show`, piped through `grep A02` so only the two A02 lines (v1 and v2) are visible, JSON as returned. |
| `temperature` | `screens/temperature.jpg` | A one-off call with `temperature=0` added (snippet below) and the exact response or error the service returns. |

Temperature snippet (run from the episode folder, venv active):
```bash
PYTHONPATH=src python - <<'EOF'
import os
from triage.evaluate import make_client
client = make_client(os.environ["AZURE_OPENAI_ENDPOINT"], max_retries=0)
try:
    r = client.chat.completions.create(model="triage-mini", temperature=0,
                                       messages=[{"role": "user", "content": "Say OK"}])
    print("accepted:", r.choices[0].message.content)
except Exception as e:
    print(type(e).__name__, getattr(e, "status_code", ""), e)
EOF
```

After recording: write the real numbers into the `scorecard` narration and, if the temperature call was rejected,
the status code into the `rejected` narration (both marked `TODO` in `script.yaml`). Re-run once if a number looks
like a fluke; LLM output varies between runs, so say "in this run" in the narration.

## Masking
- Mask the resource name and endpoint host (`<resource>.openai.azure.com`), subscription name/ID, tenant name, the
  signed-in user's UPN/avatar in the portal header, and any `az account show` output. Use `pipeline/mask.js` in the
  browser; in the terminal, never echo `$AZURE_OPENAI_ENDPOINT`.
- Tickets are fictional (`Alex Demo`, Contoso); nothing else to mask in the terminal output.

## Tear-down
1. Foundry portal → **Models + endpoints** → delete `triage-mini`.
2. Remove the temporary role assignment if it was created only for the demo.
3. Keep the resource if episode 02 is recorded next; otherwise delete the resource group.
4. `deactivate && rm -rf .venv`.
