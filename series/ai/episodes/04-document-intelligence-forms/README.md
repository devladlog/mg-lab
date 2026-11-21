# DEVLADLOG AI #4 — Document Intelligence: invoices in, decisions out

Contoso's finance team receives supplier invoices as scans and phone photos. The expenses policy we indexed in
episode 3 says an invoice must show **Contoso's VAT number, the supplier's VAT number, the invoice date and the tax
amount**. This episode turns each file into a decision — **approve, review or reject** — with **Azure AI Document
Intelligence** (`prebuilt-invoice`, API `2024-11-30` v4.0 GA), our own policy and arithmetic rules, and the model's
per-field **confidence** deciding when a human must look. A bonus step turns a scanned policy page into
**Markdown** (`prebuilt-layout`) split by headings — the shape episode 3's RAG index consumes.

```
samples/*.png ──bytes──► Document Intelligence (prebuilt-invoice, keyless) ──202 + Operation-Location──► poll ──► analyzeResult
   └─► to_invoice(): typed fields (Decimal money, dates) + confidence ──► decide(): reject | review | approve ──► report / overlay
policy scan ──► prebuilt-layout, outputContentFormat=markdown ──► markdown_sections() ──► chunks for the episode 3 index
```

- **Keyless**: single-service Document Intelligence resource with a custom subdomain and `disableLocalAuth: true`;
  your user gets **Cognitive Services User**; the client uses `DefaultAzureCredential`.
- **Reject only confident facts** (a customer VAT number that isn't Contoso's, read at ≥ 0.90; a duplicate
  vendor-VAT + invoice number). **Review anything uncertain**: required field missing, confidence below the
  field's threshold, subtotal + tax ≠ total, line items ≠ subtotal, due date before invoice date, non-EUR.
- **Overlay for reviewers**: boxes drawn from each field's `boundingRegions` polygon, green above threshold,
  amber below.
- **Fictional documents only**: `invoice_intake.samples` renders five invoices (one per routing path) and a
  policy page with Pillow; nothing real goes near the service.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Document Intelligence (`kind: FormRecognizer`, F0 by default, custom subdomain, keys disabled) + Cognitive Services User for the developer |
| [`src/invoice_intake/samples.py`](src/invoice_intake/samples.py) | Renders the fictional sample invoices (clean, bad total, wrong customer, faded scan, duplicate) and a policy page |
| [`src/invoice_intake/process.py`](src/invoice_intake/process.py) | `make_client()` (keyless), `analyze_file()` (bytes → LRO → REST-shaped dict), `route_all()`, report; CLI with `--save-json` and `--replay` |
| [`src/invoice_intake/fields.py`](src/invoice_intake/fields.py) | `to_invoice()`: invoice schema fields → typed values (Decimal, date) + confidence; line items |
| [`src/invoice_intake/decide.py`](src/invoice_intake/decide.py) | Policy, thresholds and the approve / review / reject rules |
| [`src/invoice_intake/overlay.py`](src/invoice_intake/overlay.py) | Draws field polygons and confidences on the image (pixels only; PDF polygons are in inches and are refused) |
| [`src/invoice_intake/layout.py`](src/invoice_intake/layout.py) | `prebuilt-layout` with Markdown output, `markdown_sections()` (heading path, page metadata and figures dropped) |
| [`tests/`](tests) | 26 pytest tests; [`tests/fixtures.py`](tests/fixtures.py) builds synthetic analyze results in the REST shape (not captured from the service) |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                         # 26 passed (test_bicep.py is skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
PYTHONPATH=src python -m invoice_intake.samples --out samples                       # 6 PNGs, 59-130 KB each
```

What the tests cover:
- `test_sdk_and_cli.py` runs the **real `azure-ai-documentintelligence` SDK** against a local HTTP stub: the POST to
  `/documentintelligence/documentModels/prebuilt-invoice:analyze?api-version=2024-11-30&locale=en-US` with the raw
  file bytes as `application/octet-stream`, polling the `Operation-Location` until `succeeded`, a `failed`
  operation raising `HttpResponseError`, `outputContentFormat=markdown` for layout, the `--save-json` →
  `--replay` round trip.
- `test_fields_and_decide.py`: typed mapping (currency → Decimal, date), missing confidence = 0, no document = error,
  the SDK `AnalyzeResult` object maps like the JSON, and every routing rule — including "a confidently read foreign
  VAT is rejected, an uncertain one is only reviewed" and the duplicate check across a batch.
- `test_samples_and_overlay.py`: samples meet Learn's input limits (PNG, 50–10,000 px, < 4 MB for F0), sample data
  hits each rule, overlay colours by threshold, inch polygons refused.
- `test_bicep.py`: keyless single-service resource with custom subdomain, F0 default, Cognitive Services User.

Tested with Python 3.13, `azure-ai-documentintelligence 1.0.2` (targets `2024-11-30`), `azure-identity 1.27.0`,
Pillow 12.3 (`ImageFont.load_default(size=...)` needs Pillow ≥ 10.1 with FreeType).

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-docintel -l westeurope
az deployment group create -g rg-mglab-docintel -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export DOCINTEL=https://<name>.cognitiveservices.azure.com/
PYTHONPATH=src python -m invoice_intake.samples --out samples
PYTHONPATH=src python -m invoice_intake.process samples/0*.png --endpoint $DOCINTEL --save-json results/
PYTHONPATH=src python -m invoice_intake.overlay samples/04-adventure-works-faded.png results/04-adventure-works-faded.json
PYTHONPATH=src python -m invoice_intake.layout samples/contoso-expenses-policy.png --endpoint $DOCINTEL
```

## What we learned / gotchas

- **The free tier reads two pages.** Learn's service limits for F0: max 2 pages per analysis, 4 MB per file, 1
  analyze and 1 get operation per second (S0: 2,000 pages, 500 MB, 15 and 50 per second by default). A total on
  page 3 is simply absent from the result — so a missing required field routes to **review**, never "empty".
  Process files sequentially on F0.
- **Confidence is a probability estimate, not a verdict.** Learn: field confidence is between 0 and 1 and not every
  field returns one (we treat missing as 0); the transparency note recommends a pilot on your own documents to set
  straight-through vs human-review thresholds (its example: 0.80). Our 0.85–0.90 per-field values are starting
  points for money and identifiers, not recommendations.
- **Never auto-reject on an uncertain read.** One misread digit in a VAT number would otherwise bounce a valid
  supplier invoice. Rejects require a confident read; everything else is a review.
- **Money is Decimal.** `valueCurrency.amount` is a JSON number; we quantize to cents immediately so
  `subtotal + tax == total` is an exact comparison with a one-cent tolerance.
- **Entra ID needs a custom subdomain and a single-service resource.** Learn: regional endpoints don't support
  Microsoft Entra authentication, and the role for calling the API is **Cognitive Services User**. Role assignments can
  take up to 5 minutes to apply.
- **Polygons are pixels for images, inches for PDF** (the page `unit`). The overlay refuses inch polygons rather
  than drawing boxes in the wrong place.
- **Layout Markdown carries page metadata in HTML comments** (`<!-- PageBreak -->`, `<!-- PageNumber="1" -->`) and
  figures in `<figure>` tags; strip them before chunking or they end up in your search index.
- **The SDK refuses bearer tokens over plain HTTP**, so the stub tests use a fake `AzureKeyCredential`; real runs
  are keyless.

## References

- [Invoice model (v4.0)](https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/invoice?view=doc-intel-4.0.0) and the [invoice field schema 2024-11-30](https://github.com/Azure-Samples/document-intelligence-code-samples/blob/main/schema/2024-11-30-ga/invoice.md)
- [Service quotas and limits](https://learn.microsoft.com/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0) — F0: 2 pages, 4 MB, 1 TPS
- [Interpret and improve accuracy and confidence scores](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/accuracy-confidence?view=doc-intel-4.0.0)
- [Transparency note for Document Intelligence](https://learn.microsoft.com/azure/foundry/responsible-ai/document-intelligence/transparency-note) — pilot-based thresholds, human in the loop
- [SDK target: REST API v4.0](https://learn.microsoft.com/azure/ai-services/document-intelligence/versioning/sdk-overview-v4-0?view=doc-intel-4.0.0) — Entra auth needs a custom subdomain; Cognitive Services User
- [Authenticate requests to Foundry Tools](https://learn.microsoft.com/azure/ai-services/authentication#authenticate-with-microsoft-entra-id)
- [Layout model](https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0), [Markdown output elements](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/markdown-elements?view=doc-intel-4.0.0) and [RAG with Document Intelligence](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/retrieval-augmented-generation?view=doc-intel-4.0.0)
- [v4.0 migration guide](https://learn.microsoft.com/azure/ai-services/document-intelligence/versioning/migration-guide-overview?view=doc-intel-4.0.0) — v3.0 API end of support 30 March 2029; use 2024-11-30
- [Azure built-in roles (Cognitive Services User)](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#cognitive-services-user)
- Blog: [Document Intelligence — Complete Guide](https://www.devladlog.com/articles/ai/2026-06-04-document-intelligence-complete-guide-2026/)
