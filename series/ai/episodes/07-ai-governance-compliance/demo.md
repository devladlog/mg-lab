# Demo shot list — DEVLADLOG AI #7 (AI governance and compliance)

Everything in `src/`, `governance/` and `infra/` is tested locally (30 pytest tests, Bicep build + lint). The four
`screen` scenes **need the lab subscription and the lab tenant**: three show Azure Policy and the evidence pack against
real resources, one shows Purview Compliance Manager.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner) — €30/month budget alert already set |
| Resource group | `rg-mglab-ai-07`, region **Sweden Central** |
| Policy assignments (RG scope, free) | `ai-keyless-deny` (built-in `71ef260a-…`, Deny) · `ai-approved-models-deny` (built-in `aafe3651-…`, Deny, asset IDs gpt-5-mini 2025-08-07 and text-embedding-3-small 1) · `ai-diagnostic-logs-audit` (built-in `1b4d1c4e-…`, AuditIfNotExists) |
| Log Analytics workspace | PerGB2018, 30-day retention; receives the HR account's Audit / RequestResponse / AzureOpenAIRequestUsage logs (a few MB at most: no model calls in this episode) |
| Azure OpenAI `mglab-gov-aoai-…` | kind `OpenAI`, S0, keyless, tags `ai-system-id=hr-bot`, guardrail `contoso-hr-strict`, deployment `chat` = gpt-5-mini 2025-08-07 **DataZoneStandard**, capacity 10, NoAutoUpgrade. Idle = no charge (pay per token, nothing is called) |
| Azure OpenAI `mglab-gov-shadow-…` | kind `OpenAI`, S0, keyless, **untagged, no diagnostic settings, no deployments** (the deliberate shadow resource). Idle = no charge |
| Purview | Lab tenant E5 trial (until 20 Dec 2026): Compliance Manager, one premium AI regulation (EU Artificial Intelligence Act). Learn: E5 can use three premium regulations free; **check the licence counter on the Regulations page first** — trial behaviour not verified |
| Roles | `labadmin`: Owner on the subscription (deploys policy assignments, runs the evidence pack); Compliance Manager Administrator (or Compliance Administrator) in Purview |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI, VS Code; browser for Purview |
| Lab users | Not changed. Owners in the register are fictional names only. |

**Estimated cost for the recording window:** policy assignments are free; idle Azure OpenAI accounts and deployments
cost nothing; Log Analytics ingestion is a few MB (pay-as-you-go per GB) — expected well under €1. Delete the resource
group the same day.

**Needs verification before recording:**
- gpt-5-mini 2025-08-07 DataZoneStandard quota in Sweden Central (fallback `chatSku='Standard'` or `GlobalStandard`;
  GlobalStandard makes MOD-03 FAIL for hr-bot — say so on camera if you use it).
- That the approved-models policy (mode `Microsoft.CognitiveServices.Data`) denies the gpt-4.1-nano deployment made
  through the CLI. Learn says a Deny assignment makes the deployment fail; if it doesn't in the lab, keep the take and
  show the evidence pack reporting MOD-01 FAIL instead (script TODO).
- That gpt-4.1-nano 2025-04-14 GlobalStandard exists in Sweden Central; any model **not** in the allowed list works for
  the deny test (`az cognitiveservices model list -l swedencentral -o table`).

## Setup (off camera)

```bash
cd series/ai/episodes/07-ai-governance-compliance
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                   # expect 30 passed
az login                                                    # labadmin, off camera
az group create -n rg-mglab-ai-07 -l swedencentral
az deployment group create -g rg-mglab-ai-07 -f infra/main.bicep -p infra/main.bicepparam \
   --query properties.outputs -o json > /tmp/ai07-outputs.json      # don't show on camera
export AOAI_NAME=$(jq -r .aoaiName.value /tmp/ai07-outputs.json)
export SUB=$(az account show --query id -o tsv)             # never echo it
```

Wait **at least 15 minutes** (Learn) after the deployment before filming the deny scenes. Then start a compliance
scan and wait for it to finish (it can take a while; `--no-wait` and check later):
`az policy state trigger-scan --resource-group rg-mglab-ai-07`.

Before the RAI-02 line is filmed, update `governance/register.yaml` → `hr-bot.rai_gate.date/verdict` to the recorded
episode 6 gate (TODO comments in the file). The evidence pack uses today's date; a gate older than 90 days FAILS.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user/host name), wide enough for the evidence table
(~150 columns) or reduce the font slightly for that scene.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `deny-keys` | `screens/deny-keys.jpg` | `az cognitiveservices account create -g rg-mglab-ai-07 -n contoso-keys-test -l swedencentral --kind OpenAI --sku S0 --custom-domain contoso-keys-test --yes` → error `RequestDisallowedByPolicy`, assignment `ai-keyless-deny`, the non-compliance message. |
| `deny-model` | `screens/deny-model.jpg` | `az cognitiveservices account deployment create -g rg-mglab-ai-07 -n $AOAI_NAME --deployment-name nano --model-name gpt-4.1-nano --model-version 2025-04-14 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 1` → policy violation naming `ai-approved-models-deny` and the message. |
| `evidence-run` | `screens/evidence-run.jpg` | `PYTHONPATH=src python -m aigov.evidence --register governance/register.yaml --subscription $SUB --resource-group rg-mglab-ai-07 --save-snapshot reports/snapshot.json ; echo exit=$?` → hr-bot block (11 controls), `UNREGISTERED  mglab-gov-shadow-…: no ai-system-id tag`, two `(info)` lines, `RESULT: FAIL`, `exit=1`. |
| `compliance-manager` | `screens/compliance-manager.jpg` | Purview portal → Compliance Manager → **Regulations**, "Premium AI templates" with *EU Artificial Intelligence Act*; create assessment "HR assistant: EU AI Act" (group: new "AI systems"); open one improvement action → **Evidence** tab → **Add evidence** → **Document** → upload `reports/evidence-hr-bot.txt`; the file appears in the list. |

If the deny-model command *succeeds*, delete that deployment right after the take
(`az cognitiveservices account deployment delete -g rg-mglab-ai-07 -n $AOAI_NAME --deployment-name nano`) and record
the evidence-run take while it still exists, so MOD-01 shows FAIL. Update the script TODOs either way.

Optional (not a screen scene): Azure portal → Policy → Compliance filtered to `rg-mglab-ai-07`, to confirm the shadow
account is non-compliant for `ai-diagnostic-logs-audit`.

## Masking

- Mask the subscription ID, tenant name, signed-in user and the resource name suffixes in the portal
  (`pipeline/mask.js`). The CLI error for the deny scenes prints the full resource ID including the subscription:
  **blur the subscription GUID** in those two captures.
- Don't `echo $SUB`; don't show `/tmp/ai07-outputs.json` or `reports/snapshot.json` (it contains resource IDs).
- The evidence report header says "subscription (masked)" by design; resource names `mglab-gov-…` can stay if the
  suffix is blurred.
- Purview: mask the tenant name, the user's UPN and the organisation's compliance score.

## Tear-down

```bash
az group delete -n rg-mglab-ai-07 --yes      # removes accounts, workspace and the RG-scoped policy assignments
# Cognitive Services accounts are soft-deleted; purge both to release the names:
az cognitiveservices account purge -g rg-mglab-ai-07 -n $AOAI_NAME -l swedencentral
az cognitiveservices account purge -g rg-mglab-ai-07 -n $(jq -r .shadowName.value /tmp/ai07-outputs.json) -l swedencentral
rm -rf reports /tmp/ai07-outputs.json; deactivate; rm -rf .venv
```

Purview: delete the "HR assistant: EU AI Act" assessment (Compliance Manager → Assessments → ⋯ → Delete) unless you
want to keep it for the next episodes; note that an activated premium regulation keeps counting toward the free
three for the licence period (Learn: licences for activated regulations are good for one year).
