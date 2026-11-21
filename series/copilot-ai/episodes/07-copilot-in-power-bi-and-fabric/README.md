# DEVLADLOG Copilot & AI #7 - Copilot in Power BI and Fabric

Contoso's finance team asks: *can we just switch Copilot on for the Contoso Bikes report?* The honest answer has three
parts, and this episode builds something you can run for each:

- **What it needs and costs.** Copilot in Power BI and Fabric has no per-user licence. It needs a paid Fabric capacity
  F2 or higher (or Premium P1 or higher) and burns capacity units per token. `copilot_pbi cost` turns the published
  rates into numbers; `Get-FabricCopilotCapacity.ps1` reads the real Fabric REST API and says which of your workspaces
  sit on a capacity that can run Copilot.
- **What makes it answer correctly.** The model has to be prepared: descriptions, unambiguous names, AI instructions,
  verified answers. `copilot_pbi lint` reads the TMDL of the Contoso Bikes model from
  [Power BI episode 1](../../../power-bi/episodes/01-data-modeling-star-schema/) and finds what Copilot will trip over;
  `describe` writes the fixes as `///` descriptions into a copy; the AI instructions text is linted against the model so
  a renamed or hidden measure is caught.
- **How to know it answered correctly.** `golden` computes the validated answer to five test questions straight from the
  CSV files (Decimal arithmetic, no Power BI), as Learn recommends: expected measure, grouping, date basis, validated result.

Series plan: [`../../README.md`](../../README.md) ("Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 6, *Copilot in Power Automate*. Next: episode 8, [*Copilot in Dynamics 365 Sales and Customer
Service*](../08-copilot-in-dynamics-365-sales-and-customer-service/). Category episodes this builds on:
[Power BI 1: data modeling and star schema](../../../power-bi/episodes/01-data-modeling-star-schema/) (the model),
[Power BI 5: row-level security](../../../power-bi/episodes/05-row-level-security/),
[Power BI 6: dashboards and publishing](../../../power-bi/episodes/06-dashboards-publishing/).

**Lab licensing reality (read first).** Per Learn, the Fabric **trial** capacity does not support Copilot. The lab has a
Fabric trial, so every real Copilot screen of this episode needs a **paid F2** that the owner approves
(about 0.395 EUR per hour while it runs, see `demo.md`). Nothing in this folder fakes a Copilot answer.

| Path | What it is |
|---|---|
| [`src/copilot_pbi/tmdl.py`](src/copilot_pbi/tmdl.py) | Small TMDL reader: tables, columns, measures, `///` descriptions, hidden, format, aggregation. Skips fenced and multi-line expressions |
| [`src/copilot_pbi/lint.py`](src/copilot_pbi/lint.py) | Model rules C001-C010, AI instruction rules A001-A004, verified-answer plan rules V001-V005, each tied to a Learn statement |
| [`src/copilot_pbi/describe.py`](src/copilot_pbi/describe.py) | Copies a model and adds descriptions (and extra measures) from a JSON spec; never changes the source, never overwrites an existing description |
| [`src/copilot_pbi/cost.py`](src/copilot_pbi/cost.py) | Copilot in Fabric capacity estimate from the documented token rates (100 / 10 / 400 CU seconds per 1,000 tokens) |
| [`src/copilot_pbi/golden.py`](src/copilot_pbi/golden.py) | Validated answers for five golden questions from the star-schema CSVs of Power BI episode 1 |
| [`src/copilot_pbi/cli.py`](src/copilot_pbi/cli.py) | `python -m copilot_pbi lint / cost / golden / describe` |
| [`src/scripts/Get-FabricCopilotCapacity.ps1`](src/scripts/Get-FabricCopilotCapacity.ps1) | Real collector: Fabric REST `GET /v1/capacities` and `GET /v1/workspaces` with continuation paging; read-only; needs a token |
| [`src/data/descriptions-contoso-bikes.json`](src/data/descriptions-contoso-bikes.json) | Descriptions (first 200 characters carry the meaning) and one new measure, `Orders Shipped` |
| [`src/data/ai-instructions-contoso-bikes.md`](src/data/ai-instructions-contoso-bikes.md) | The AI instructions text to paste into *Prep data for AI* (about 1,000 characters of the 10,000 allowed) |
| [`src/data/verified-answers-plan.json`](src/data/verified-answers-plan.json) | Our own planning format for three verified answers, checked against the documented limits (it is not a Microsoft file) |
| [`tests/`](tests) | 25 pytest tests + 15 Pester tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (16 scenes, about 870 words) and recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/07-copilot-in-power-bi-and-fabric
python3 -m pip install -r src/requirements.txt        # pytest only: the tool is standard library
python3 -m pytest -q                                   # 25 passed
pwsh -NoProfile -Command "Invoke-Pester -Path tests/Get-FabricCopilotCapacity.Tests.ps1 -Output Minimal"   # 15 passed (Pester 6.2)
cd src
M=../../../../power-bi/episodes/01-data-modeling-star-schema/src/ContosoSales.SemanticModel
python3 -m copilot_pbi lint $M                         # before: 0 errors, 7 warnings
python3 -m copilot_pbi describe $M data/descriptions-contoso-bikes.json --out /tmp/ContosoSales.Prepared
python3 -m copilot_pbi lint /tmp/ContosoSales.Prepared --instructions data/ai-instructions-contoso-bikes.md \
        --verified data/verified-answers-plan.json --fail-on info     # after: clean, exit 0
python3 -m copilot_pbi golden                          # the five validated answers
python3 -m copilot_pbi cost --sku F2 --prompts-per-day 20 --price-per-cu-hour 0.1975 --window-hours 3
```

Against the tenant (needs the tenant, read-only):

```powershell
Connect-AzAccount            # signed-in session of the lab admin; never paste a password or token in a file
./src/scripts/Get-FabricCopilotCapacity.ps1 | Format-Table -AutoSize
```

Verified here: pytest 25 passed (Python 3.13), Pester 15 passed (PowerShell 7.6). The Pester tests use a mocked
`Invoke-RestMethod` (tests only). **Not verified without the tenant:** the first real run of the script, whether
Power BI Desktop opens the described copy with the extra measure, and every answer Copilot gives.

## What we learned / gotchas

- **Trial capacity: no Copilot.** Four Learn pages say it (Copilot overview, Enable Copilot for Power BI, Fabric features
  by SKU, troubleshooting after a trial). One page (*Overview of Copilot for Data Engineering and Data Science*) lists
  "Trial capacities are also supported" in its known-limitations table: it contradicts the others, so the demo records
  what the product really does on the trial workspace and the script says so.
- **No per-user licence, and Pro/PPU alone is not enough.** Copilot consumes capacity units. Pro and PPU workspaces need a
  *Fabric Copilot capacity* (F2/P1 or higher, tenant home region only) assigned to the user. A new or resized capacity
  can take up to 24 hours before Copilot works: **create the F2 the day before.**
- **Cost model.** Per 1,000 tokens: input 100 CU seconds, cached input 10, output 400. Copilot operations are *background*
  jobs, smoothed over 24 hours. Learn's example (2,000 in, 500 out = 400 CU seconds = 6.67 CU minutes; 13,824 requests
  a day on an F64) is a test here. A pay-as-you-go F SKU is billed per second while it runs, used or not, so pausing is the
  only cost control. With our assumed prompt size (8,000 input, 600 output tokens: an **assumption**, not a Microsoft
  number) one prompt costs 1,040 CU seconds, so an F2 (172,800 CU seconds a day) is exhausted by about 166 such prompts a
  day: keep the recording to a handful of prompts and watch the Capacity Metrics app.
- **Standalone Copilot is retiring.** Learn marks standalone Copilot in Power BI and app-scoped Copilot as retiring
  (announcement at aka.ms/PBINov26, which blocks automated fetches: not read here), "Copilot within reports isn't
  affected". The successor, *Microsoft Copilot in Power BI and Fabric* (preview, setting off by default), answers
  questions about Power BI data with Fabric IQ and "you don't need ... an F SKU" for it; Work IQ (mail, meetings,
  documents) needs a Microsoft 365 Copilot licence (series episode 2 and 1). We demo the report pane, which is GA.
- **Prep data for AI is stored on the semantic model**, not the report. Q&A must be turned on for the model or the tabs are
  disabled. You cannot upload instructions in Desktop: paste them. After every change close and reopen the Copilot pane.
  AI instructions are limited to 10,000 characters, visible only to authors, and only interpreted. Verified answers:
  250 per model, 15 trigger phrases each, 500 characters per phrase, 10 filter permutations. Q&A itself is going away in
  February 2027 per the verified-answers article; Copilot is the replacement.
- **Descriptions count only up to 200 characters** (Copilot in the DAX query view and the optimisation article), so the
  meaning goes first. `C003` flags longer ones.
- **Hidden fields are not seen.** The model context Copilot builds for data questions excludes hidden fields and tables
  marked private; so an AI instruction that names a hidden column does nothing (`A004`). The *AI data schema* starts
  without hidden fields. Copilot in the DAX query view does see hidden objects.
- **Instructions cannot repair the model.** Learn: "additional instructions can't correct inaccurate relationships or
  inappropriate aggregations". That is why the `describe` spec adds an `Orders Shipped` measure (`USERELATIONSHIP` on
  the inactive ship-date relationship) instead of only writing "use ship date" in the instructions.
- **Real finding in the category model:** 9 orders were shipped in January 2026, but the date table of Power BI episode 1
  covers 2024-2025, so they fall outside it (`Orders Shipped` cannot see them). The golden question uses June 2025,
  where orders (145) and shipments (149) differ.
- **Same column name in two tables** (`Country` in Customer and Store) is the classic ambiguity; `C009` stays until both
  copies carry a description, and the AI instructions tell Copilot to ask.
- **Copilot is nondeterministic.** Learn: the same input does not always give the same output. If you ask the same prompt on
  an unchanged model within 24 hours you get the cached answer. The golden questions are a regression test, not a guarantee.
- **Approved for Copilot** (formerly "prepped for AI") removes the friction treatment in standalone Copilot; you cannot
  mark a report, dashboard or app, only the semantic model.
- **Region.** West Europe is an EU region: Learn requires the cross-geo tenant setting only for capacities outside the US
  and the EU data boundary. The lab capacity therefore needs no cross-geo consent; confirm on the tenant settings screen.
- **SKU strings.** `Get-FabricCopilotCapacity.ps1` accepts `F2` and above and `P1` to `P5`, and reports a paused capacity
  (`state` other than `Active`) as not capable. The exact SKU string a trial capacity returns from the API is not
  documented on the REST page, so trial is recognised by pattern (`trial`, `FT...`) and anything else that is not F2+/P1-P5
  is reported "not capable" with the SKU shown. Region support and the tenant settings are not checked by the script:
  compare the Region column with the region availability page and read the settings in the admin portal.

## References

Microsoft Learn
- [Copilot for Power BI overview](https://learn.microsoft.com/power-bi/create-reports/copilot-introduction)
- [Enable Fabric Copilot for Power BI](https://learn.microsoft.com/power-bi/create-reports/copilot-enable-power-bi)
- [Prepare your data for AI](https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai) (AI data schemas, verified answers, instructions, Approved for Copilot)
- [AI instructions](https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai-instructions) and [AI data schemas](https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai-data-schema) and [Verified answers](https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai-verified-answers)
- [Optimize your semantic model for Copilot in Power BI](https://learn.microsoft.com/power-bi/create-reports/copilot-evaluate-data)
- [Use Copilot with semantic models](https://learn.microsoft.com/power-bi/create-reports/copilot-semantic-models)
- [Enable and configure Copilot in Microsoft Fabric](https://learn.microsoft.com/fabric/fundamentals/copilot-enable-fabric)
- [Fabric Copilot capacity](https://learn.microsoft.com/fabric/enterprise/fabric-copilot-capacity)
- [Consumption rates and billing for Copilot in Fabric](https://learn.microsoft.com/fabric/fundamentals/copilot-fabric-consumption) and [How Copilot in Microsoft Fabric works](https://learn.microsoft.com/fabric/fundamentals/how-copilot-works)
- [Troubleshoot Copilot unavailability after a trial expires](https://learn.microsoft.com/fabric/fundamentals/troubleshoot-copilot-unavailable-after-trial)
- [Microsoft Fabric features by SKU and capacity type](https://learn.microsoft.com/fabric/enterprise/fabric-features)
- [Copilot and Agent tenant settings](https://learn.microsoft.com/fabric/admin/service-admin-portal-copilot)
- [Release status of AI and Copilot experiences in Fabric](https://learn.microsoft.com/fabric/fundamentals/copilot-ai-feature-state)
- [Microsoft Copilot in Power BI and Microsoft Fabric (preview)](https://learn.microsoft.com/fabric/iq/connectors/copilot-power-bi-fabric)
- [Overview of Copilot for Data Engineering and Data Science (preview)](https://learn.microsoft.com/fabric/data-engineering/copilot-notebooks-overview) and [chat pane](https://learn.microsoft.com/fabric/data-engineering/copilot-notebooks-chat-pane)
- [Tabular Model Definition Language (TMDL)](https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview)
- REST: [List Capacities](https://learn.microsoft.com/rest/api/fabric/core/capacities/list-capacities), [List Workspaces](https://learn.microsoft.com/rest/api/fabric/core/workspaces/list-workspaces)
- [P SKU to F SKU mapping](https://learn.microsoft.com/power-bi/support/premium-migration-decision-guide#map-your-p-sku-to-an-f-sku)

Price (not on Learn): Azure Retail Prices API (`https://prices.azure.com/api/retail/prices`), filter
`serviceName eq 'Microsoft Fabric' and armRegionName eq 'westeurope'`, currency EUR, read 21 Nov 2026: the meters *Compute
Pool*, *Power BI* and *Copilot and AI* **Capacity Usage** are each listed at 0.1975 EUR per CU hour, so an F2 (2 CU) is
0.395 EUR per hour of running time (list price, check the Azure calculator at recording time). The public Azure pricing
page serves placeholder prices to automated fetches, so it was not used.

No devladlog.com blog guide: this series is built from vendor documentation only.
