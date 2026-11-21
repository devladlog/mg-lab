# DEVLADLOG Power BI #16: AI Insights and Smart Narratives

Same **Contoso Bikes** star schema as episodes 1-13. This episode puts the four AI visuals of Power BI on it: **key influencers**,
**decomposition tree**, **anomaly detection** and **smart narrative** (Custom mode), and, for each one, a way to check the answer
before you show it: a readiness check of the data and the model against the limits on Microsoft Learn, and a plain-Python reference.

Blog guide: <https://www.devladlog.com/articles/power-bi/2026-06-03-ai-insights-complete-guide-2026/>
(its code was not used: see "Not verified / not done").

**Draft status.** The code and its tests are done and run here. The AI visuals themselves are built **by hand in Power BI Desktop on
camera** (see [demo.md](demo.md)): I could not verify the PBIR `visualType` names of the AI visuals, so no generated visual JSON is shipped.

| Path | What it is |
|---|---|
| [`src/data/generate_export.py`](src/data/generate_export.py), [`build_star.py`](src/data/build_star.py) | Copies of the episode 4 data scripts (seed 42, 2024-2025): the star schema |
| [`src/data/build_order_profile.py`](src/data/build_order_profile.py) | One row per order: `Order Size` and `Delivery` (plain rules) and a **simulated** `Survey Rating` with a planted effect of Delivery and Channel |
| [`src/ai_readiness.py`](src/ai_readiness.py) | Rules AI001-AI009: the Learn limits of key influencers and anomaly detection, plus the `discourageImplicitMeasures` conflict. Exit code 1 on any error |
| [`src/reference_insights.py`](src/reference_insights.py) | The directional reference: rate-inside / rate-outside ratio per Explain by value, candidate anomaly days (robust z-score), the expected text of the narrative measures |
| [`src/ContosoSalesAI.SemanticModel/`](src/ContosoSalesAI.SemanticModel) | TMDL: the episode 4 model **without** `discourageImplicitMeasures`, plus the table `Order Profile`, its measures, a relationship to `Date`, and three `Narrative *` measures on `Sales` |
| [`src/ContosoSalesAI.Report/`](src/ContosoSalesAI.Report), [`ContosoSalesAI.pbip`](src/ContosoSalesAI.pbip) | An empty PBIR report with one blank page `AI insights`: the canvas for the visuals built on camera |
| [`tests/`](tests) | pytest, 47 tests (below) |

## Run it

```bash
# from the episode folder (needs pytest, PyYAML, jsonschema, referencing)
python3 -m pytest tests -q          # 47 passed

# the data, by hand
cd src/data
python3 generate_export.py --out raw/sales_export.csv
python3 build_star.py --src raw/sales_export.csv --out star
python3 build_order_profile.py --star star        # 2,440 orders; 289 Low ratings
cd ..
python3 ai_readiness.py --star data/star --model ContosoSalesAI.SemanticModel/definition      # no findings, exit 0
python3 reference_insights.py --star data/star    # influencers, candidate anomaly days, expected narrative text
```

To open the model in Desktop: copy `data/star` to the recording laptop, set the `DataFolder` parameter (`expressions.tmdl`, keep the trailing backslash), open `ContosoSalesAI.pbip`.

What the 47 tests cover: the profile has one row per order, its totals equal the fact table, the derived columns follow their rules, it is
deterministic and the planted effect is really in it; every readiness rule fires on a small broken input and stays quiet on the real data (and the
episode 4 model is flagged AI007); the reference ranks the planted drivers first, computes the ratio as Learn describes it, flags a planted spike
and not a flat series; the TMDL is consistent (tabs only, every `[Measure]` and `Table[Column]` resolves, the columns map to the CSV header, the
relationship targets real columns, `discourageImplicitMeasures` is absent); the `.pbip`, `.pbir` and all PBIR files validate against Microsoft's
published JSON schemas (vendored in `tests/schemas`); and `script.yaml` follows the series brief and every code scene is a real excerpt of `src/`.

Expected values for seed 42 (from `reference_insights.py`): Delivery is Slow 20.4 % low vs 6.0 % (3.40x), Channel is Online 17.4 % vs 10.5 % (1.65x),
Contains Bike 1.18x; first candidate anomaly day 2024-06-05; narrative for 2025: *Sales were 967,473 in the selected period.* / *That is 8.1% above the same period last year.* / *Bikes leads the mix.*

## Needs Desktop / tenant / licence

- **Power BI Desktop (free), no tenant:** building and showing all four visuals, the model, the narrative measures (the DAX was **not** evaluated anywhere in the container: there is no DAX engine; it is checked only for structure and references).
- **Lab tenant + trial capacity:** only the gotcha screen (what Copilot mode shows on the trial workspace).
- **Paid capacity (F2 or higher, or P1 or higher):** Copilot mode of the Narrative visual and Copilot generally. **Not bought, not shown**: that is the owner's decision (an F2 is billed while it runs; check the current price on the Azure pricing page before deciding).

## Not verified / not done

1. **The AI visuals themselves.** Nothing here was opened in Desktop. What each visual shows (order of influencers, the AI splits, which days are marked, how a narrative reads) must be recorded on the day; the reference only says what to expect. SR-CNN and the regression are not re-implemented.
2. **PBIR for the AI visuals** is not generated (unverified `visualType` names). The empty report uses `"themeCollection": {}`; it is schema-valid, but whether Desktop opens it without complaint is untested.
3. **Learn conflict on Q&A:** the Q&A pages say it goes away in **February 2027**, the January 2026 monthly update says it is deprecated in **December 2026**. The script says to plan for the earlier date.
4. **Learn conflict on trials:** the *Copilot for Power BI overview* says trial capacities are not supported; the Fabric notebook Copilot page lists a trial as eligible. The script follows the Power BI page.
5. **The rating is simulated** (planted effect). Nothing in the episode is a finding about a real business; the script and the code say so.
6. The blog guide's code was not used and not checked.

## References (Microsoft Learn)

- Key influencers: <https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-influencers>
- Decomposition tree: <https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-decomposition-tree>
- Anomaly detection: <https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-anomaly-detection>
- Smart narrative: <https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-smart-narrative>
- Copilot for Power BI (requirements): <https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-introduction>
- Copilot unavailable after a trial: <https://learn.microsoft.com/en-us/fabric/fundamentals/troubleshoot-copilot-unavailable-after-trial>
- Q&A limitations (deprecation notice): <https://learn.microsoft.com/en-us/power-bi/natural-language/q-and-a-limitations>
- Monthly updates archive (Q&A deprecation, January 2026): <https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-latest-update-archive>
- Analytics pane (Anomalies settings): <https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-analytics-pane>
