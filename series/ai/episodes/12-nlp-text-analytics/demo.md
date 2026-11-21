# Demo shot list — DEVLADLOG AI #12 (NLP and text analytics)

Everything in `src/` and `infra/` is tested locally (50 pytest tests, Bicep build + lint) with the real SDK against a
stand-in service. The four `screen` scenes **need the lab subscription**: every result on screen comes from the real
Azure Language service. No M365 tenant objects are used. The recording shows what the service really returned; a leaked
string, a wrong label or a failed gate is the episode, not a retake.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-12`, region **West Europe** |
| Language resource | `mglab-nlp-lang-…`, kind `TextAnalytics`, **Free F0** (Bicep parameter `skuName`), custom subdomain, keys off |
| Roles (Bicep) | `labadmin`: **Cognitive Services Language Reader** on the resource |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI; browser on the lab tenant for the Azure portal |

**Estimated cost for the recording window:** F0 is free up to 5,000 text records per month (Learn). `python -m ticketnlp
limits` estimates one full run of the 13 tickets (the five features summed, worst case) at under 100 records, so `show`,
`analyze` and `evaluate --compare` together are a few hundred records even with retakes. If F0 is exhausted or unavailable
the S tier is billed per text record; the price is on https://aka.ms/unifiedLanguagePricing, which I could not check
without a subscription, so none is embedded. Delete the resource group the same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **One F0 per subscription.** Learn's limits pages for the custom features say one F0 Language resource per subscription.
   If the deployment is refused for that reason, redeploy with `-p skuName=S` and say so in the voice over.
2. **Language Reader is enough?** Learn's role definition lists `Language/analyze-text/action` for Language Reader, and the
   SDK posts to `/language/:analyze-text`, so it should work (allow ~5 minutes after the assignment). If a 403 appears,
   the honest fix is to change the role in `infra/main.bicep` to Cognitive Services User
   (`a97b65f3-24c7-4388-baec-2e87135dc908`), update the Bicep test, and say why in the narration TODO of `resource-screen`.
3. **Entra scope.** The SDK asked the credential for `https://cognitiveservices.azure.com/.default` in the local tests.
   Confirm against the real resource with `show` (a 401 means the role has not propagated or the endpoint is not the
   custom-subdomain one).
4. **Detection of the planted strings.** Names (`Alex Demo`, `Taylor Demo`, …), the e-mail addresses and the phone numbers
   (`+351 912 345 678`, `961 234 567`) are fictional. Whether the service detects every one, in both languages and
   formats, is exactly what `evaluate` measures. Do not edit the cases to make the table greener. The badge `CON-48213`
   is caught by the local backstop, not the service.
5. **Language labels.** `pt` is expected for Portuguese (pt-PT is returned as `pt` by the SDK; confirm). The
   `mixed-language` case has no label on purpose; show what the service says, and the confidence.
6. **Sentiment labels are ours.** `en-mixed-laptop` and `pt-mixed-email` are judgement calls ("mixed"). If the service
   disagrees, say so; the sentiment gate is 75 % over 10 labelled cases, so one or two misses are expected.
7. **Opinion mining.** `analyze_sentiment(show_opinion_mining=True)` should return targets such as VPN or printer. If a
   target list is empty for a ticket, show it as it is.
8. **The long thread.** `long-thread` is 5,860 characters: two chunks, each below 5,120. If the service rejects either,
   the error code appears in the table and is the finding.

## Setup (off camera)

```bash
cd series/ai/episodes/12-nlp-text-analytics
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 50 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-12 -l westeurope
az deployment group create -g rg-mglab-ai-12 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai12-outputs.json   # don't show this file on camera
export TICKETNLP_ENDPOINT=$(jq -r .languageEndpoint.value /tmp/ai12-outputs.json)
export PYTHONPATH=src
```

Wait ~5 minutes for the role assignment. Dry run off camera: `python -m ticketnlp show --id en-neg-vpn`.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user or host name). The tickets are fictional, so the
`original` line may be on screen; the report and the JSON never contain ticket text.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `show-screen` | `screens/show.jpg` | `python -m ticketnlp show --id en-neg-vpn`: `original` (fictional name, phone, e-mail), `redacted`, `PII removed`, sentiment with scores, `aspects`, key phrases, entities, `next step`. |
| `resource-screen` | `screens/resource.jpg` | Azure portal → the Language resource: Overview (pricing tier, region, endpoint masked), authentication/keys view showing local authentication disabled, Access control (IAM) with the Language Reader assignment. Mask subscription, tenant, user and the name suffix. |
| `analyze-screen` | `screens/analyze.jpg` | `python -m ticketnlp analyze --out build/report.md` and the printed Markdown: language, sentiment, next step, PII categories, key phrases, aspects, not-analysed list, requests, text-record estimate. |
| `evaluate-screen` | `screens/evaluate.jpg` | `python -m ticketnlp evaluate --compare ; echo exit=$?`: both rows, problem / mismatch / LEAK lines, the RESULT line, the exit code. |

After recording, update the TODO comments in `script.yaml` with what the service returned, including leaks and a failed gate.
Keep `build/` until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). Don't `echo`
  `$TICKETNLP_ENDPOINT`; don't show `/tmp/ai12-outputs.json`.
- All tickets, names, phone numbers, e-mail addresses and the badge number are fictional (`Alex Demo`, `*.demo@contoso.com`,
  `CON-48213`). Do not type or paste any real text into a live take.
- Don't show the pricing page or Cost Management with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-12 --yes
az cognitiveservices account purge -g rg-mglab-ai-12 -n <languageName> -l westeurope
rm -rf /tmp/ai12-outputs.json build; deactivate; rm -rf .venv
```

Deleting the resource group removes the account. Purge it so the soft-deleted resource name is released.
Confirm in Cost Management the next day that nothing in `rg-mglab-ai-12` is still billing.
