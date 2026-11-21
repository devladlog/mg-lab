# Demo shot list — DEVLADLOG AI #4 (Document Intelligence and forms)

Everything in `src/` and `infra/` is tested locally (26 pytest tests, Bicep build + lint, the sample generator).
The four `screen` scenes **need the lab tenant**: they show real analyze results from the service.

## Prerequisites
- Lab subscription where you can create a resource group and **assign roles** (Owner or User Access Administrator
  on the resource group) — the Bicep assigns *Cognitive Services User* to you.
- One **Azure AI Document Intelligence** resource, **F0 (free)** by default — no cost. F0 limits (Learn): first 2
  pages per document, 4 MB per file, 1 analyze + 1 get request per second. The samples are single-page PNGs under
  200 KB and the CLI processes them one by one, so F0 is enough. If an F0 resource can't be created in the lab
  subscription, set `sku = 'S0'` in `infra/main.bicepparam`: S0 is pay per page; the whole
  demo is a few dozen pages.
- **Needs verification before deploying:** that Document Intelligence (v4.0, `2024-11-30`) is available in the
  region you pick (default in README: `westeurope`) — Learn: *Document Intelligence region support*.
- Local: Azure CLI, Python 3.10+, Bicep CLI, VS Code (for the JSON screen), an image viewer.

## Setup (lab tenant, off camera)
```bash
cd series/ai/episodes/04-document-intelligence-forms
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                      # expect 26 passed
az login                                                       # lab user, off camera
az group create -n rg-mglab-docintel -l westeurope
az deployment group create -g rg-mglab-docintel -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/docintel-outputs.json   # don't show this file on camera
export DOCINTEL=$(jq -r .endpoint.value /tmp/docintel-outputs.json)
PYTHONPATH=src python -m invoice_intake.samples --out samples
```
Wait ~5 minutes for the role assignment (Learn: up to five minutes to propagate). Warm-up, off camera:
`PYTHONPATH=src python -m invoice_intake.process samples/01-fabrikam-clean.png --endpoint $DOCINTEL` must print one
row. A `401`/`403` means the role hasn't propagated yet (or the endpoint isn't the custom-subdomain one).
Delete any `results/` folder from the warm-up so the recorded run starts clean.

## Screens to capture (1920×1080, dark theme, font ≥ 16 pt)

Record `run` first (it creates `results/`), then `field-json`, `overlay`, `layout`.

| Scene id | File | What must be on screen |
|---|---|---|
| `run` | `screens/run.jpg` | Terminal: `PYTHONPATH=src python -m invoice_intake.process samples/0*.png --endpoint $DOCINTEL --save-json results/` — the table (file, vendor, total, total confidence, decision, reasons) for the five samples and the `approve / review / reject` counts. |
| `field-json` | `screens/field-json.jpg` | VS Code with `results/01-fabrikam-clean.json`, folded so `documents[0].fields.InvoiceTotal` is visible: `type: currency`, `valueCurrency` (amount, currencyCode EUR), `content`, `confidence`, `boundingRegions` with the polygon. |
| `overlay` | `screens/overlay.jpg` | `PYTHONPATH=src python -m invoice_intake.overlay samples/<file>.png results/<file>.json` for an invoice that went to **review** (prefer `04-adventure-works-faded`; otherwise `02-northwind-bad-total`), opened full screen in an image viewer: green/amber boxes with field names and confidences. |
| `layout` | `screens/layout.jpg` | Terminal: `PYTHONPATH=src python -m invoice_intake.layout samples/contoso-expenses-policy.png --endpoint $DOCINTEL` — the Markdown with `#`/`##` headings, then `[Travel and expenses > Submitting expense claims] … chars` lines. |

After recording, fill the TODOs in `script.yaml`:
- `run`: what happened to the faded `04` scan (approved, or review and which field), and confirm `03` was rejected
  (if it went to review because `CustomerTaxId` was read below 0.90, say so — it's the rule working).
- `layout`: confirm the headings came back as Markdown headings; if the model returned them as plain paragraphs,
  say that honestly in the narration.
- Optionally copy the five `results/*.json` into `tests/` as a second, *captured* fixture set (they contain only
  fictional data) and add a replay test.

## Masking
- Mask the resource name and endpoint (`mglab-docintel-…cognitiveservices.azure.com`), subscription name/ID,
  tenant name and the signed-in user if any portal page appears (`pipeline/mask.js`). Use `$DOCINTEL`; don't
  `echo` it and don't show `/tmp/docintel-outputs.json`.
- Vendor names (Fabrikam, Northwind, Tailspin, Adventure Works, Contoso), addresses, VAT numbers (`PT 000 000 000`
  etc.) and amounts are fictional and can stay on screen. Every sample says "Fictional document for a demo".

## Tear-down
```bash
az group delete -n rg-mglab-docintel --yes
# Cognitive Services accounts are soft-deleted; purge to release the name:
az cognitiveservices account purge -g rg-mglab-docintel -n <docintel-name> -l westeurope
rm -rf samples results /tmp/docintel-outputs.json; deactivate; rm -rf .venv
```
