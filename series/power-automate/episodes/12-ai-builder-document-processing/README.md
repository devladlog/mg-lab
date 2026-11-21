# DEVLADLOG Power Automate #12: The model read it. Should you trust it?

AI Builder's prebuilt **invoice processing** model reads an invoice and gives every field a confidence score. This
episode builds the part around it: **check the file before spending credits**, **write the extraction to a staging
list**, and let a second flow **decide** (auto-post, review, reject) with rules that are tested on a laptop.

The scenario continues the IT helpdesk of episodes 1-11: Finance drops supplier invoices (fictional: Adatum Office
Supplies invoicing Contoso Ltd) in a SharePoint library, and the IT-owned flows keep the bad ones away from the
Invoices list.

- **`invoicekit preflight`** checks a PDF, PNG or JPEG against the limits Learn lists (type, 20 MB, 50 to 10,000 px,
  17 x 17 inches, 2,000 pages) and, for a PDF with several invoices, prints the **Pages** value for each one.
- **`invoicekit triage`** applies the decision rules to an extraction (the staging-list columns): missing fields, low
  confidence, subtotal + tax against total, amount limit, date sanity, duplicates.
- **Solution `ITInvoiceIntake`** (`src/solution/`): the flow *Triage invoice extraction* that applies the **same
  rules as flow expressions**, with the thresholds in environment variables. `tests/test_flow_parity.py` runs the
  flow in the flowkit simulator and the Python on the same cases and requires the same decision.
- **Sample files** (`src/samples/`, made by `tools/make_samples.py`) and **hand-written extraction rows**
  (`src/extractions/`, labelled as mocks in each file).
- **The AI Builder extraction flow is not in the repo.** We could not verify the action's operation id and output paths
  without the tenant, so [`demo.md`](demo.md) builds it in the designer (six steps) and asks to export it afterwards.

| Path | What it is |
|---|---|
| [`src/invoicekit/preflight.py`](src/invoicekit/preflight.py) | File checks (P00-P06) and `split_invoices` (Pages ranges) |
| [`src/invoicekit/triage.py`](src/invoicekit/triage.py) | `decide()`: auto-post, review or reject, with reasons; `Config` thresholds |
| [`src/solution/`](src/solution) | Solution 1.0.0.0 unpacked (`pac solution unpack` layout): 1 flow, 7 environment variables, 2 connection references, `<Managed>2</Managed>` (as in episode 9) |
| [`src/tools/build_solution.py`](src/tools/build_solution.py) · [`make_samples.py`](src/tools/make_samples.py) | Write `solution/` and `samples/` (idempotent) |
| [`src/samples/`](src/samples) | `invoice-clean.pdf`, `invoice-two-in-one.pdf`, `invoice-mismatch.pdf`, `invoice-oversize.pdf`, `invoice-scan.png`, `invoice-tiny.png` |
| [`src/extractions/`](src/extractions) | 8 mock rows + `known.json` (already-posted invoices) |
| [`src/flowkit/`](src/flowkit) | Lint and dry-run harness from episodes 1-11 |
| [`tests/`](tests) | 64 pytest tests: preflight (16), triage (22), flow parity (19, a grid of 360 combinations among them), solution and `pac` (7) |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ with `pytest`, `pyyaml`, `pypdf` and `Pillow`; `reportlab` only to regenerate the samples. `pac` is
optional (its test is skipped without it; no sign-in is needed).

```bash
cd series/power-automate/episodes/12-ai-builder-document-processing
python -m pytest                      # 64 passed in ~30 s (pac 2.16.1)

cd src
python -m invoicekit preflight samples/*
python -m invoicekit triage extractions/*.json --today 2026-11-10 --known extractions/known.json
python -m invoicekit triage extractions/clean.json --amount-limit 500 --today 2026-11-10
python -m flowkit lint solution/Workflows/*.json                       # OK
pac solution pack --zipfile ../out/ITInvoiceIntake.zip --folder solution --packagetype Managed
python tools/make_samples.py ; python tools/build_solution.py          # rewrite samples/ and solution/
```

`preflight` exits 1 if any file is refused; `triage` exits 1 if any decision is not `auto-post`.

```
$ python -m invoicekit preflight samples/*
OK       invoice-clean.pdf
ERROR    P05 invoice-oversize.pdf page 1: 20.0 x 20.0 inches is over 17 x 17
ERROR    P06 invoice-tiny.png: 40 x 40 px is under the 50 x 50 minimum
OK       invoice-two-in-one.pdf
         2 invoices in one file, one flow run each:
           Pages = 1     INV-2026-0412
           Pages = 2-3   INV-2026-0413
$ python -m invoicekit triage extractions/total-mismatch.json --today 2026-11-10
REVIEW     total-mismatch.json
           MISMATCH: subtotal 170 + tax 34 is not total 250
```

## How the material was made, and what still needs the tenant

The file limits, the field names, the **Pages** behaviour and the prices were read from Learn (links below). The sample
PDFs are generated with reportlab and the scan with Pillow, all fictional. **The extraction rows are written by hand**:
they have the columns the demo's extraction flow writes, they are mocks and say so (`_note`), and no test claims they
are what AI Builder returns. The triage flow was run in the flowkit simulator with mocks for SharePoint and Outlook
(the mock for the duplicate query parses the `$filter` the flow built). `pac solution pack` and `create-settings` run
for real.

**Needs tenant:** the billing plan and Copilot Credits, the extraction flow, real model output on the sample files,
importing the solution and the flow turning on, the Outlook message, and every `screen` scene. See
[`demo.md`](demo.md). The demo costs about 10 pages x 8 Copilot Credits = $0.80 at pay-as-you-go (Learn rate table).

## What we learned / gotchas

1. **The model reads; it doesn't decide.** Learn's output table is fields plus a confidence score (0 to 1) for most of
   them. Everything that follows (thresholds, limits, who looks) is your design. The thresholds here (0.8 for every
   required field, 5,000 total, 365 days) are **our choices**; Learn only shows 0.65 as the point where its examples try
   a second model.
2. **A good read of a bad invoice.** `total-mismatch.json` has high confidence on every field and still goes to review,
   because subtotal + tax is not the total. The rule needs a score nowhere. (`test_fixtures_with_a_known_invoice`)
3. **Use the `(number)` and `(date)` outputs.** Learn lists each amount twice: "as it's written on the invoice" (text)
   and in "standardized number format". The rules compare numbers and dates, so the demo maps those.
4. **Floating point at the cent.** 100 + 20 - 120.01 is 0.010000000000005 in binary floating point, so "tolerance 0.01"
   rejected a one-cent difference until we added an epsilon (Python) and compared with 0.010001 (flow). Boundary tests:
   `test_rounding_difference_of_one_cent...`, `test_one_cent_boundary...`.
5. **Don't rely on `if`, `and`, `or` to skip evaluation.** The flowkit simulator evaluates all arguments before calling
   the function, so `if(isnull(x), false, add(x, 1))` fails on null. `abs` is not among the functions flowkit supports, so the flow uses
   `max(a - b, b - a)`, and every operand is wrapped in `coalesce(..., 0)` behind a null test. We did not check whether
   the service short-circuits; the null-safe form works either way.
6. **One invoice per Pages range.** Learn: a range with two invoices "will return partial data" of both. `split_invoices`
   finds where each invoice starts in a PDF with a text layer (an `INVOICE` heading and an invoice number label near the
   top, not "continued" or "page 2 of ..."). **It can't read a scan** (no text layer) and its heuristic is ours, not
   Learn's.
7. **Duplicates are exact.** Same vendor and invoice id, compared after trim and lower case; the flow asks SharePoint
   with a `$filter` (apostrophes doubled, `test_vendor_with_an_apostrophe...`). `INV-2026-0412` and `INV20260412` are
   different to it (`test_duplicate_match_ignores_case...`). The flow only checks the **Invoices** list: an invoice
   waiting for review is not yet a duplicate.
8. **Limits to know.** Per environment, 360 calls per 60 seconds across the document models (Learn). The image minimum
   is 50 x 50 px and the PDF page maximum 17 x 17 inches; a PDF over 2,000 pages is processed only up to page 2,000
   (our P04 warning).
9. **Licensing moved.** Learn: **AI Builder credits are ending**
   (announced October 2025; seeded credits in licences run to the end of the contract, add-ons can be bought only by
   existing customers until 1 November 2026). Invoice processing is **8 Copilot Credits per page** ($0.08 at
   pay-as-you-go, $0.01 per credit); in flows, AI Builder credits are used first, then Copilot Credits; without any, runs
   are blocked (`EntitlementNotAvailable`, `QuotaExceeded`). Pay-as-you-go is available for **production and sandbox**
   environments only. Testing prebuilt models in the AI hub consumes no credits.
10. **Learn disagrees with itself about premium.** *Overview of licensing*: "A Power Automate flow that uses any AI
    Builder action is a premium flow", billed also through the cloud flow run meter under pay-as-you-go. *Licensing and
    AI Builder credits*: "adding an AI Builder action to a flow doesn't transform it into a premium flow". The demo uses
    the Premium trial either way; record what the maker portal shows.

### What was not verified here

- **The AI Builder action in flow JSON**: its operation id, parameter names (`Pages`, the file) and output paths. That
  is why it is not in the repo. The mapping in `demo.md` uses the names Learn gives for the designer outputs.
- That the **solution files import** into the real service and the triage flow turns on and triggers on rows created by
  the extraction flow (same caveat as episode 9; `demo.md` step 4 says what to do if it fails). `Customizations.xml`,
  the connection references and the `PostItem`/`PatchItem` parameter names (`item/Decision/Value` for a choice column)
  follow episodes 1-10, which have the same caveat.
- **What the model returns for our sample files**, especially the noisy scan: it is a synthetic image and the model may
  read little or nothing from it. Nothing here claims otherwise.
- **Which "Power Platform product" to select** in the billing plan so that AI Builder runs bill as Copilot Credits.
  Learn's setup page says to select the product the meters apply to and doesn't spell this out for AI Builder in Power
  Automate.
- The **date columns** (date only) as the trigger returns them, compared with `ticks()`: only tested with ISO strings.
- Custom models, the Pages parameter on a real run, and the receipt model are not covered.

## References

- [Invoice processing prebuilt AI model (fields, confidence scores, file limits, 360 calls per 60 s, key-value pairs)](https://learn.microsoft.com/ai-builder/prebuilt-invoice-processing)
- [Use the invoice processing prebuilt model in Power Automate (action, outputs, Pages parameter, one invoice per range)](https://learn.microsoft.com/ai-builder/flow-invoice-processing)
- [Overview of licensing: AI Builder capability rate table (8 Copilot Credits per page, $0.08)](https://learn.microsoft.com/ai-builder/administer-licensing)
- [Licensing and Copilot Credits (consumption rates, AI Builder activity)](https://learn.microsoft.com/ai-builder/message-management) · [Licensing and AI Builder credits (order of consumption, overage errors, free testing)](https://learn.microsoft.com/ai-builder/credit-management) · [End of AI Builder credits](https://learn.microsoft.com/ai-builder/endofaibcredits)
- [Monitor AI Builder models and prompts activity (Automation Center, AI Builder activity)](https://learn.microsoft.com/ai-builder/activity-monitoring)
- [Set up pay-as-you-go (billing plan in the admin center, production and sandbox environments)](https://learn.microsoft.com/power-platform/admin/pay-as-you-go-set-up) · [Pay-as-you-go plan overview](https://learn.microsoft.com/power-platform/admin/pay-as-you-go-overview)
- [pac solution (pack, create-settings, import)](https://learn.microsoft.com/power-platform/developer/cli/reference/solution)
- Blog: [AI Builder Document Processing: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-06-08-ai-builder-processing-complete-guide-2025/)
