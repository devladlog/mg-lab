# Demo shot list — Power BI #16 AI Insights and Smart Narratives

## Lab environment

No VM. Everything but the gotcha screen runs in **Power BI Desktop on the Windows recording laptop** with local CSV files.

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current), Python 3.11+ for the two terminal insets, Windows Terminal | free |
| Data | `src/data/star` rebuilt with the three data scripts (see README), copied to `C:\MGLab\power-bi\star\` | free |
| Model | `src/ContosoSalesAI.pbip`; set the `DataFolder` parameter to `C:\MGLab\power-bi\star\` (trailing backslash), Refresh | free |
| Gotcha screen only | Lab tenant, workspace `Contoso Sales (Lab)` on the Fabric trial capacity (West Europe), account `labadmin` | trial, €0 |
| Copilot mode | needs a paid F2+/P1+ capacity: **not in this plan, owner's decision**; the episode shows what the trial refuses | not bought |

## What was verified where

| Step | In the container | On the recording day |
|---|---|---|
| Data, readiness rules, reference numbers, TMDL structure, PBIP/PBIR schema | 47 pytest tests | opening the project in Desktop |
| The three Narrative measures | structure and references only (no DAX engine) | evaluate in Desktop, compare with the expected text below |
| All four AI visuals | nothing | build and record; compare with `reference_insights.py` |
| Copilot mode message on trial | nothing | gotcha screen |

## Setup (off camera, once)

1. Rebuild the star schema and the order profile (README, "Run it"), copy `star` to the laptop. Open `ContosoSalesAI.pbip`, set `DataFolder`, Refresh. If Desktop refuses the empty report, create a new report in Desktop on the same model and note it in the README.
2. In a terminal: `python src/ai_readiness.py --star <star> --model src/ContosoSalesAI.SemanticModel/definition` must print `no findings`. Then `python src/reference_insights.py --star <star>` and keep the output at hand.
3. On page **AI insights** add: Key influencers, Decomposition tree, a line chart, a Narrative visual, a Year slicer, one visual per screen below (or one page per visual).

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `influencers` | `screens/key-influencers.jpg` | Key influencers: **Analyze** `Order Profile[Survey Rating]`, state **Low**; **Explain by** Channel, Store Country, Customer Country, Contains Bike, Lines, Delivery; **Expand by** empty. Key influencers tab: select bubble 1 (expect **Delivery is Slow**, about 3.4x, 20.4 % vs 6.0 %) and bubble 2 (expect **Channel is Online**, about 1.65x). Then **Top segments**. Optional: add `Ship Days` to Explain by to show it competes with `Delivery` (same information). Record what really appears |
| `tree` | `screens/decomposition-tree.jpg` | Decomposition tree: **Analyze** `Sales[Sales Amount]`, **Explain by** Product Category, Subcategory, Store Channel, Store, Customer Country. Plus next to the root, **High value**: show the light bulb and its tooltip. **Low value**. Format, Analysis type: **Absolute** vs **Relative**, note the difference |
| `anomaly` | `screens/anomaly-detection.jpg` | Line chart, Axis `Date[Date]` (continuous), Values `Sales Amount`, **no legend**. Analytics pane, **Anomalies** on. Click one marked point: the Anomalies pane with explanations and strength. Inset: `python src/reference_insights.py` candidate days (2024-06-05 first). Write down whether Desktop marks the same days |
| `narrative` | `screens/smart-narrative.jpg` | Narrative visual, **Custom** mode. Edit the text, insert the values with **Value**: `Narrative Sales`, `Narrative YoY`, `Narrative Top Category`. Slicer Year 2025, expected: *Sales were 967,473 in the selected period.* *That is 8.1% above the same period last year.* *Bikes leads the mix.* Year 2024: *There is no prior-year period to compare with.* Learn lists "dynamic values and conditional formatting" under narrative limitations: if a text measure does not work as a Value, put the three measures in cards and say so |
| `gotcha` | `screens/copilot-trial.jpg` | Workspace `Contoso Sales (Lab)` on the trial capacity: Narrative visual, Copilot mode. Show the exact message (Learn quotes: "Copilot isn't available because none of your workspaces have the necessary capacity assigned"). Switch to Custom. Record the real wording and adjust the narration if it differs. **Do not buy or assign a paid capacity** |

## Write down (the README's "Not verified" list)

1. Does key influencers rank Delivery is Slow, then Channel is Online, as the reference does? Does Contains Bike appear? Any warning shown?
2. Do the AI splits of the tree pick the fields you expect? What does Relative change?
3. Which days does the anomaly visual mark in the daily line? The same as the reference?
4. Do the three Narrative measures evaluate to the expected text? Do they work as dynamic Values?
5. The exact message of Copilot mode on the trial workspace.
6. Does Desktop open `ContosoSalesAI.pbip` (empty report, `themeCollection` empty) without a repair prompt?

## Masking

Blur: tenant name and the sign-in domain in the account menu and in any workspace URL, workspace and report IDs in the address bar. The data is fictional; no
other blur is needed. Use `labadmin` or the demo users only.
