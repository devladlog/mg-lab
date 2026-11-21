# Demo shot list — DEVLADLOG AI #2, Azure OpenAI enterprise patterns

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant apps | none |
| Lab user | `labadmin` (the recording account): Owner on the subscription, runs `az login` and the deployment |
| Azure | Resource group **`rg-mglab-ai-02`** in **Sweden Central**, deployed by `infra/main.bicep`: API Management **Basic v2** (billed per hour while it exists: roughly €1 for a 3-hour recording window, check the pricing page), two Azure OpenAI accounts (Sweden Central + Germany West Central, gpt-5-mini 2025-08-07 Data Zone Standard, 10k TPM each: tokens only, cents), Application Insights + Log Analytics (ingestion: cents). Deploy right before recording; tear-down deletes the group and purges both soft-deleted services |
| Licences / trials | none beyond the subscription |
| Recording machine | The Windows lab laptop: Foundry/Azure portal in the browser, bash terminal in WSL (Ubuntu) with Azure CLI, Python 3.10+ and this folder (the commands below are bash) |

Code scenes and the test output are already real (from this folder). The four `screen` scenes need a deployment in
the lab subscription. Status: **needs tenant** for everything on screen; tests, `bicep build` and `bicep lint` run
offline.

## Prerequisites
- Lab Azure subscription with the budget alert. You need Owner (or Contributor + User Access Administrator) on the
  resource group, because the template creates role assignments.
- **Cost:** API Management **Basic v2** is billed for as long as it exists, plus tokens on two gpt-5-mini
  deployments and a little Log Analytics ingestion. Check the
  [API Management pricing](https://azure.microsoft.com/pricing/details/api-management/) and
  [Azure OpenAI pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/) pages before
  recording. Deploy right before the session and delete right after (tear-down below).
- **Model availability:** check on Learn (*Foundry Models sold by Azure → model availability*, Data Zone Standard
  tab) that `gpt-5-mini` `2025-08-07` is offered as **Data Zone Standard** in both regions of `main.bicepparam`
  (Sweden Central, Germany West Central). If not, pick two EU regions where it is, and check you have 10k TPM of
  quota in each.
- Local: Azure CLI, Python 3.10+, Bicep CLI, this folder.

## Setup (lab tenant)
```bash
cd series/ai/episodes/02-azure-openai-enterprise-patterns
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                   # expect 37 passed
az login                                                    # labadmin, off camera
az group create -n rg-mglab-ai-02 -l swedencentral
az deployment group create -g rg-mglab-ai-02 -f infra/main.bicep -p infra/main.bicepparam \
   --query properties.outputs -o json > /tmp/aoai-outputs.json          # don't show this file on camera
```
Then:
1. Portal → API Management → **APIs → Azure OpenAI (v1) via gateway → All operations → Policies**: confirm the
   policy from `infra/policies/aoai-api.xml` is there and saved without errors.
   **Needs verification:** the `llm-*` policies are documented for LLM APIs. If the deployment or the policy editor
   rejects them on this API, delete the `aoai` API, re-create it with **+ Add API → Microsoft Foundry** (select the
   primary account, client compatibility **Azure OpenAI v1**, base path `aoai`), paste `aoai-api.xml` as its policy,
   and note the change in README.
2. APIM → **Subscriptions** → `hr-bot` and `sales-copilot` → copy each primary key into a shell variable without
   echoing it:
   ```bash
   export APIM_GATEWAY_URL=https://<apim-name>.azure-api.net
   read -rs HR_KEY; read -rs SALES_KEY
   ```
3. Warm-up (off camera): `APIM_SUBSCRIPTION_KEY=$SALES_KEY PYTHONPATH=src python -m aoai_gateway.smoke --requests 1`
   must print one `200` line. `404`: check the deployment name `chat` and the API path. An authorization error
   (`401`/`403`): check the key; right after deployment, also wait 5 minutes — Learn notes a new Cognitive Services
   OpenAI User assignment can take up to 5 minutes to take effect — and retry.
4. Wait at least a minute after the warm-up so the token-per-minute counter is fresh.

## Screens to capture (1920×1080, dark terminal theme, font ≥ 16 pt)

| Scene id | File | What must be on screen |
|---|---|---|
| `deployed` | `screens/deployed.jpg` | Portal, resource group `rg-mglab-ai-02` overview: API Management service (Basic v2), two Azure OpenAI accounts with their two regions in the Location column, Application Insights, Log Analytics workspace. |
| `burst` | `screens/burst.jpg` | Terminal: `APIM_SUBSCRIPTION_KEY=$HR_KEY PYTHONPATH=src python -m aoai_gateway.smoke --requests 12` — the `remaining-this-minute` values going down, the `429 throttled retry-after=…` rows, the summary and the token CSV. If no 429 appears, raise `--requests` (the limit is 2,000 tokens per minute per subscription). |
| `other-team` | `screens/other-team.jpg` | Immediately after `burst`: `APIM_SUBSCRIPTION_KEY=$SALES_KEY PYTHONPATH=src python -m aoai_gateway.smoke --requests 2` showing `200` lines. |
| `metrics` | `screens/metrics.jpg` | Application Insights → **Metrics** → metric namespace `aoai-gateway` → total tokens, **Apply splitting** by `Subscription ID`, last 30 minutes. Custom metrics can take a few minutes to show up; record this screen last. |

After recording, fill the `TODO` in the `burst` narration of `script.yaml` (how many calls succeeded before the first
429 in this run).

Optional B-roll (not in the script): portal → APIM → **Backends** → `aoai-pool` showing the two members with
priorities 1 and 2, and the circuit-breaker rule on `aoai-primary`.

## Masking
- Never show subscription keys: don't open **Show/hide keys** on camera, and use `read -rs` as above.
- Mask the APIM name and gateway host (`<apim-name>.azure-api.net`), the account names
  (`mglab-aoai-p-…`, `mglab-aoai-s-…`), subscription name/ID, tenant name and the signed-in user in the portal header
  (`pipeline/mask.js`). Don't show `/tmp/aoai-outputs.json` or `az account show`.
- Team names (`hr-bot`, `sales-copilot`) and the Contoso publisher are fictional and can stay.

## Tear-down
```bash
az group delete -n rg-mglab-ai-02 --yes
# Both services are soft-deleted; purge them so nothing lingers (names come from /tmp/aoai-outputs.json):
az apim deletedservice purge --service-name <apim-name> --location swedencentral
az cognitiveservices account purge -g rg-mglab-ai-02 -n <primary-account> -l swedencentral
az cognitiveservices account purge -g rg-mglab-ai-02 -n <secondary-account> -l germanywestcentral
rm /tmp/aoai-outputs.json; deactivate; rm -rf .venv
```
API Management soft-delete keeps the instance for 48 hours (name not reusable) unless purged.
