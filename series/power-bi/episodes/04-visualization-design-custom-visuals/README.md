# DEVLADLOG Power BI #4: Visualization Design & Custom Visuals

Same fictional **Contoso Bikes** semantic model as [episode 2](../02-advanced-dax/) (star schema + the advanced DAX
measures). This episode is about what sits on top of it, built so it can be checked before anyone opens Desktop:

- **An accessible report theme** (`src/themes/ContosoBikes.json`): validated against Power BI Desktop's published
  theme schema, and checked by **`theme-check`** for text contrast (4.5:1, the Learn accessibility checklist), data
  colour contrast (3:1, WCAG non-text contrast) and colour vision deficiency (simulated protanopia, deuteranopia,
  tritanopia, CIEDE2000 colour difference)
- **A report page as code** (`src/tools/build_report.py`): a 12-column grid spec on a 1280 x 720 page generates the
  PBIR report folder (enhanced report format, one JSON file per visual); every file is validated against
  Microsoft's published JSON schemas (vendored, with all the schemas they reference)
- **`report-lint`**: design and accessibility rules on PBIR (page bounds, overlaps, 8 px grid, alt text present and
  ≤ 250 characters, titles, tab order = reading order, hard-coded colours, visual count, fields that don't exist in
  the TMDL model)
- **Target bullet**, a **custom visual** in TypeScript (`src/target-bullet`): actual vs target per category,
  colour **plus** a direction marker and a signed percentage, Windows high-contrast support, rendering events, no
  `innerHTML`, no web access; pure logic unit-tested with `node --test`, packaged with `pbiviz` 7.2.1

| Path | What it is |
|---|---|
| [`src/themes/ContosoBikes.json`](src/themes/ContosoBikes.json) | The report theme (8 data colours, good/neutral/bad, structural colours, text classes, visual styles) |
| [`src/tools/theme_check.py`](src/tools/theme_check.py) | `theme-check`: rules TC001–TC004 |
| [`src/tools/build_report.py`](src/tools/build_report.py) | Layout spec → `src/ContosoSales.Report/` (`--check` fails on drift) |
| [`src/tools/report_lint.py`](src/tools/report_lint.py) | `report-lint`: rules RL001–RL010 |
| [`src/ContosoSales.Report/`](src/ContosoSales.Report) | Generated PBIR report: page *Sales overview*, 7 visuals, custom theme registered in `report.json` + `StaticResources/RegisteredResources/` |
| [`src/ContosoSales.SemanticModel/`](src/ContosoSales.SemanticModel), [`src/ContosoSales.pbip`](src/ContosoSales.pbip) | Episode 2 model (TMDL), unchanged |
| [`src/target-bullet/`](src/target-bullet) | The custom visual: `capabilities.json`, `pbiviz.json`, `src/model.ts` (logic), `src/view.ts` (SVG node tree), `src/settings.ts` (format pane), `src/visual.ts` (glue), `test/*.test.ts` |
| [`src/data/`](src/data) | Episode 1 generator + star builder (the tests compute the numbers the recorder must see) |
| [`tests/`](tests) | pytest: theme, report (schemas + lint + layout), expected numbers |
| [`tests/fixtures/messy-report/`](tests/fixtures/messy-report) | A schema-valid page that breaks every `report-lint` rule |
| [`tests/fixtures/learn-example-theme.json`](tests/fixtures/learn-example-theme.json) | The example theme colours from Learn's *Create custom report themes* page (our "before") |
| [`tests/schemas/`](tests/schemas) | Vendored schemas: PBIR/PBIP from developer.microsoft.com, theme schema 2.159 (Oct 2026) from `microsoft/powerbi-desktop-samples`; `fetch_schemas.py` re-downloads them |

## The page

```
 24 ┌ Sales amount ┐┌ Sales growth ┐┌ Orders ──────┐┌ Year ────────┐
    └──────────────┘└──────────────┘└──────────────┘└──────────────┘
152 ┌ Sales amount and prior year by month ─────────┐┌ by category ─┐
    │                     lineChart                 ││ clusteredBar │
    └───────────────────────────────────────────────┘└──────────────┘
432 ┌ Products ranked inside their category ┐┌  (free: Target bullet) ┐
    │               tableEx                 ││                        │
    └───────────────────────────────────────┘└────────────────────────┘
     x = 24 + 104 * column, width = 104 * span - 16   (12 columns, 8 px grid)
```

## Run it

```bash
python3 src/tools/theme_check.py src/themes/ContosoBikes.json            # 0 error(s), 0 warning(s), exit 0
python3 src/tools/theme_check.py tests/fixtures/learn-example-theme.json # 1 error(s), 4 warning(s), exit 1
python3 src/tools/build_report.py --check                                # report matches the spec
python3 src/tools/report_lint.py src/ContosoSales.Report --model src/ContosoSales.SemanticModel/definition
#   0 error(s), 0 warning(s)
python3 src/tools/report_lint.py tests/fixtures/messy-report --model src/ContosoSales.SemanticModel/definition --max-visuals 2
#   4 error(s), 7 warning(s), exit 1
python3 -m pytest tests -q                                               # 36 passed

cd src/target-bullet
npm ci --no-audit --no-fund
npm test                                     # tsc + node --test: 16 passed
npx pbiviz package --certification-audit     # lint, "No external requests found in the visual.", Package created!
#   -> dist/contosoTargetBullet7C1E2A9B4D5F4E0A8B3C6D2E1F0A9B8C.1.0.0.0.pbiviz (about 6 KB)
```

In the video, `theme-check` and `report-lint` are short for `python3 src/tools/theme_check.py` and
`python3 src/tools/report_lint.py`. The `.pbiviz` isn't committed (build output); build it as above.

## Expected results (computed by `tests/test_expected.py`, Year slicer = 2025)

| Visual | Expected |
|---|---|
| Cards | Sales amount **967,472.88** · Sales growth vs prior year **8.1%** · Orders **1,268** |
| Target bullet (Category, Sales Amount vs Sales PY) | Accessories 130,320.98 vs 120,256.62 **▲ +8.4%** · Bikes 780,356.80 vs 716,095.45 **▲ +9.0%** · Clothing 56,795.10 vs 58,577.03 **● -3.0%** (on target at 5 % tolerance; **▼** below at 2 %) |
| theme-check, Learn example | good #1AAB40 vs bad #D64554: colour difference 74.0 with normal vision, **5.6** with simulated deuteranopia |

## What we learned / gotchas

- **The documentation's own example colours fail the accessibility guidance.** Learn's *Create custom report
  themes* example uses green for good and red for bad; Learn's *Design reports for accessibility* lists green and red
  as a combination to avoid. Simulated deuteranopia puts that pair 5.6 apart (CIEDE2000), where 74 is the difference
  with normal vision. Our theme uses blue / burnt orange for good / bad (56.2 apart under deuteranopia) and the
  custom visual never relies on colour alone.
- **The theme schema is strict about property names** (`additionalProperties: false` at the top level: a typo like
  `dataColours` is rejected) but not everywhere inside `visualStyles`: a misspelled property inside a card (we tried
  `positon`) passes the schema. Desktop shows an error on import for unrecognized fields (Learn); we haven't tested
  how it treats this case.
- **A hand-registered custom theme may not be picked up.** Learn says every RegisteredResources file needs an entry
  in `report.json` and that edits are supported *for resources Desktop already registered*. Our `report.json`
  registers the theme the way Desktop does, but if Desktop ignores it, Design > Import theme with the same file is
  the fallback (demo.md step 3); after that, the file in `RegisteredResources` is the source of truth.
- **`pbiviz package` fails on `"strict": true`** in the visual's `tsconfig.json`: the generated
  `.tmp/precompile/visualPlugin.ts` doesn't compile under strict null checks
  (`'VisualConstructorOptions | undefined' is not assignable`). We keep the pbiviz tsconfig non-strict and compile
  the logic and its tests with a separate strict `tsconfig.test.json`.
- **`pbiviz package` writes outside the project**: the first run generated a developer certificate in the user's
  home folder (`pbiviz-certs`), even though packaging doesn't need it. It also writes `webpack.statistics.prod.html`
  into the project folder.
- **Importing a visual from a file now needs developer mode in Desktop**, for the current session only (Learn:
  File > Options and settings > Options > Current file > Report settings > *Develop a visual*).
- **pbiviz lists optional features we didn't implement**: keyboard navigation (`supportsKeyboardFocus`), selection,
  context menu, tooltips, highlight, landing page, localization. The visual is readable by screen readers
  (`role="img"`, a `<title>` and `aria-label` per row) but not navigable point by point with the keyboard. Those are
  certification-relevant follow-ups, not done here.
- **Not verified on this machine (needs Power BI Desktop on Windows):** the generated report has never been opened
  in Desktop; visual role names (`Values`, `Category`, `Y`) and the literal formats follow PBIR files Desktop writes,
  and the schemas accept them, but only Desktop proves it. The custom visual has never rendered in Power BI: logic,
  view tree and packaging are tested, the DOM glue in `visual.ts` is not.

## References
- [Use report themes](https://learn.microsoft.com/power-bi/create-reports/desktop-report-themes) · [Create custom report themes (schema, dataColors, good/neutral/bad, textClasses, visualStyles)](https://learn.microsoft.com/power-bi/create-reports/report-themes-create-custom) · [Report theme JSON schema (GitHub)](https://github.com/microsoft/powerbi-desktop-samples/tree/main/Report%20Theme%20JSON%20Schema)
- [Design Power BI reports for accessibility (4.5:1, alt text 250 characters, tab order, colour combinations to avoid, high contrast)](https://learn.microsoft.com/power-bi/create-reports/desktop-accessibility-creating-reports)
- [Power BI project report folder (PBIR, RegisteredResources, schemas)](https://learn.microsoft.com/power-bi/developer/projects/projects-report)
- [Set up the environment for a Power BI visual (developer mode)](https://learn.microsoft.com/power-bi/developer/visuals/environment-setup) · [Visual project structure (20 x 20 icon)](https://learn.microsoft.com/power-bi/developer/visuals/visual-project-structure) · [Visual API](https://learn.microsoft.com/power-bi/developer/visuals/visual-api)
- [Rendering events](https://learn.microsoft.com/power-bi/developer/visuals/event-service) · [High-contrast mode support](https://learn.microsoft.com/power-bi/developer/visuals/high-contrast-support) · [FormattingModel utils](https://learn.microsoft.com/power-bi/developer/visuals/utils-formatting-model)
- [Certified Power BI visuals (no fetch/XMLHttpRequest/eval/innerHTML, `--certification-audit`)](https://learn.microsoft.com/power-bi/developer/visuals/power-bi-custom-visuals-certified)
- [Import a visual from a file](https://learn.microsoft.com/power-bi/developer/visuals/import-visual) · [Manage Power BI visuals admin settings (organizational visuals, certified-only, Desktop group policy)](https://learn.microsoft.com/fabric/admin/organizational-visuals)
- Colour science: WCAG 2.1 [contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html) and [non-text contrast](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html); CVD matrices from Machado, Oliveira, Fernandes (2009); CIEDE2000 test data from Sharma, Wu, Dalal (2005)
- Blog: [Visualization Design & Custom Visuals — Complete Guide](https://www.devladlog.com/articles/power-bi/2025-03-04-visualization-design-complete-guide-2025/)
