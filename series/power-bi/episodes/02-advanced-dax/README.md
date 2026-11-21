# DEVLADLOG Power BI #2 — Advanced DAX

Same fictional **Contoso Bikes** star schema as [episode 1](../01-data-modeling-star-schema/), now with the DAX that
people actually get wrong:

- **Time intelligence** on the marked date table: prior year (`SAMEPERIODLASTYEAR`), year-over-year with variables
  and a guard for future periods, year to date (`TOTALYTD`), the last three whole calendar months (`EOMONTH` +
  `DATESBETWEEN`), and sales by **ship date** through the inactive relationship (`USERELATIONSHIP`)
- **Context transition**: "customers with more than 1,000 of sales" written right (a measure reference inside
  `FILTER`) and wrong (a raw `SUMX`), side by side
- **Ranking and share**: `RANKX` over `ALL('Product'[Product])` (rank inside the category) and `ALLEXCEPT` for the
  share of the category
- **Five saved DAX queries** (`DAXQueries/*.dax`, the files Power BI Desktop's DAX query view saves in a PBIP), two of
  them with query-scoped `DEFINE MEASURE` to show the wrong versions without polluting the model
- a **Python reference** of every measure that computes the **expected result of each query** from the CSVs, so the
  numbers are known before Desktop opens
- **`dax-lint`**, a TOM-based linter for measures and saved queries (format strings, qualified columns, unqualified
  measures, unresolved references, `/` instead of `DIVIDE`, time intelligence on a fact date column,
  `USERELATIONSHIP` on a relationship that doesn't exist)

| Path | What it is |
|---|---|
| [`src/ContosoSales.SemanticModel/definition/tables/Sales.tmdl`](src/ContosoSales.SemanticModel/definition/tables/Sales.tmdl) | 14 measures in 4 display folders (Base, Time intelligence, Ranking and share, Context transition), each with a description |
| [`src/ContosoSales.SemanticModel/DAXQueries/`](src/ContosoSales.SemanticModel/DAXQueries) | `01 Time intelligence` · `02 YoY gotcha` · `03 Context transition` · `04 Ranking and share` · `05 Ship date` |
| [`src/reference/dax_reference.py`](src/reference/dax_reference.py) | Hand-written Python equivalent of each measure and query (not a DAX engine) |
| [`src/reference/expected/`](src/reference/expected) | Expected result of each saved query (amounts 2 decimals, ratios 4 decimals, empty = BLANK) |
| [`src/DaxLint/`](src/DaxLint) | `dax-lint` (.NET 8, `Microsoft.AnalysisServices` 19.120.1); `--script` writes the TMDL view script |
| [`src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl`](src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl) | The whole model as one `createOrReplace` script (fallback for TMDL view) |
| [`src/data/`](src/data) | Generator + star CSVs (identical to episode 1; a test rebuilds them byte for byte) |
| [`src/ContosoSales.pbip`](src/ContosoSales.pbip), [`src/ContosoSales.Report/`](src/ContosoSales.Report) | Power BI Project wrapper (as in episode 1) |
| [`tests/test_reference.py`](tests/test_reference.py) | pytest: DAX semantics the reference follows (DIVIDE, BLANK arithmetic, SAMEPERIODLASTYEAR month-end extension, RANKX ties, SUMMARIZECOLUMNS blank rows...) + expected CSVs up to date |
| [`tests/test_dax_queries.py`](tests/test_dax_queries.py) | pytest: every saved query has an expected CSV with the same columns |
| [`tests/test_project_files.py`](tests/test_project_files.py) | pytest: PBIP JSON files against Microsoft's published schemas |
| [`tests/DaxLint.Tests/`](tests/DaxLint.Tests) | xUnit: the lexer, the episode model (zero findings), and the [bad-measures fixture](tests/fixtures/bad-measures) (every rule fires) |

## The measures

```dax
Sales PY            = CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date]))
Sales YoY %         = VAR CurrentSales = [Sales Amount]
                      VAR PriorSales = [Sales PY]
                      RETURN IF(NOT ISBLANK(CurrentSales), DIVIDE(CurrentSales - PriorSales, PriorSales))
Sales YTD           = TOTALYTD([Sales Amount], 'Date'[Date])
Sales Last 3 Months = VAR LastDate = MAX('Date'[Date])
                      VAR FirstDate = EOMONTH(LastDate, -3) + 1
                      RETURN CALCULATE([Sales Amount], DATESBETWEEN('Date'[Date], FirstDate, LastDate))
Sales by Ship Date  = CALCULATE([Sales Amount], USERELATIONSHIP(Sales[Ship Date], 'Date'[Date]))
Product Rank        = IF(NOT ISBLANK([Sales Amount]), RANKX(ALL('Product'[Product]), [Sales Amount]))
% of Category       = DIVIDE([Sales Amount], CALCULATE([Sales Amount], ALLEXCEPT('Product', 'Product'[Category])))
Customers Over 1K   = COUNTROWS(FILTER(VALUES('Customer'[CustomerKey]),
                          'Customer'[CustomerKey] <> -1 && [Sales Amount] > 1000))
```

## Expected results (from `src/reference/expected`)

| Query | Key values |
|---|---|
| 01 Time intelligence (2025 by month) | Jan: Sales 40,267.82 · PY 32,659.46 · YoY 23.3 % · Last 3 Months 158,840.78; Feb PY 57,494.46 (includes 29 Feb 2024); Dec YTD 967,472.88 |
| 02 YoY gotcha (by year) | 2025: YoY 8.1 %; **2026: Sales blank, PY 967,472.88, naive YoY -100 %, model YoY blank** |
| 03 Context transition (by year) | Customers Over 1K: 2024 **244**, 2025 **247**; without transition: **300** both years |
| 04 Ranking and share (2025) | Bikes: Enduro 300 rank 1, 22.4 % of category; Accessories: Rear Light Radar 1, 30.1 %; Clothing: Jersey Aero 1, 44.7 % |
| 05 Ship date (by year) | 2024: 894,929.10 by order vs 887,920.62 by ship; 2026: 5,433.00 by ship date only |

## Run it

```bash
python3 src/reference/dax_reference.py        # prints the five expected tables, rewrites expected/*.csv
python3 -m pytest tests -q                    # 40 passed

dotnet run --project src/DaxLint -- src/ContosoSales.SemanticModel/definition \
    --queries src/ContosoSales.SemanticModel/DAXQueries \
    --script src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl   # 9 PASS, 0 error(s), exit 0
dotnet run --project src/DaxLint -- tests/fixtures/bad-measures/definition \
    --queries tests/fixtures/bad-measures/queries                # 5 error(s), 5 warning(s), exit 1
dotnet test tests/DaxLint.Tests -m:1                             # Passed: 23, Failed: 0
```

In the video, `dax-lint` is short for `dotnet run --project src/DaxLint --`.

Then, on Windows: copy `src/data/star` to `C:\MGLab\power-bi\star\`, open `src/ContosoSales.pbip`, **Refresh**, open
**DAX query view**: the five saved queries appear as tabs. Run each and compare with `src/reference/expected/`
(see [demo.md](demo.md)).

## What we learned / gotchas

- **Year-over-year shows -100 % for the future.** The date table has to run to 31 December 2026 (orders placed on
  the last days of 2025 ship in January), so 2026 is a row with no sales but a prior year. `DIVIDE(Sales - PY, PY)`
  then returns -1: in DAX, BLANK behaves like zero in addition and subtraction (Learn's blank-handling table shows
  `BLANK + 5 = 5`). The model measure returns BLANK when there are no current sales.
- **Context transition is automatic only for measures.** Inside `FILTER(VALUES('Customer'[CustomerKey]), ...)`,
  `[Sales Amount] > 1000` is evaluated per customer (a measure reference in row context triggers context transition),
  but the same `SUMX(...)` written inline is evaluated once for the whole filter context: every one of the 300
  customers "qualifies".
- **`RANKX` over `ALL('Product'[Product])` ranks inside the category** when the category is also filtered: products
  of other categories evaluate to BLANK, and BLANK ranks as zero, at the bottom. The `IF(NOT ISBLANK(...))` guard
  keeps products without sales from getting a rank.
- **Money columns are fixed decimal** (`dataType: decimal`): Learn warns that `RANKX` comparisons on floating-point
  Decimal Number values can give unexpected results.
- **SAMEPERIODLASTYEAR at month level includes 29 February**: when the selection includes the last two days of a
  month, the function extends to the end of that month in the prior year. Our reference implements that rule and a
  test checks it (Feb 2025 → 29 days of Feb 2024).
- **We used `EOMONTH` + `DATESBETWEEN`** for the last three months to make the "whole calendar months" boundary
  explicit (Learn recommends `DATESINPERIOD` for standard intervals; we didn't want to rely on its month-end behaviour
  without seeing it in Desktop).
- **Not verified on this machine (needs Desktop on Windows):** the DAX itself never ran here. The queries that group
  by `'Date'[Year Month]` or filter `'Date'[Year] = 2025` expect the time-intelligence filters on `'Date'[Date]` to
  replace those filters (classic behaviour of a marked date table); if Desktop shows different values for
  `01 Time intelligence`, that assumption is the first suspect. Everything else (TMDL syntax, references, relationship
  names) was checked by TOM and `dax-lint`.
- `dax-lint` is a lexer plus rules, not a DAX parser: it doesn't type-check or evaluate expressions.

## References
- [CALCULATE (filter context, context transition)](https://learn.microsoft.com/dax/calculate-function-dax)
- [DIVIDE function vs. divide operator](https://learn.microsoft.com/dax/best-practices/dax-divide-function-operator) · [Avoid converting BLANKs to values](https://learn.microsoft.com/dax/best-practices/dax-avoid-converting-blank)
- [Column and measure references](https://learn.microsoft.com/dax/best-practices/dax-column-measure-references)
- [Data types in Power BI (blank handling)](https://learn.microsoft.com/power-bi/transform-model/desktop-data-types)
- [SAMEPERIODLASTYEAR](https://learn.microsoft.com/dax/sameperiodlastyear-function-dax) · [TOTALYTD](https://learn.microsoft.com/dax/totalytd-function-dax) · [DATESBETWEEN](https://learn.microsoft.com/dax/datesbetween-function-dax) · [DATESINPERIOD](https://learn.microsoft.com/dax/datesinperiod-function-dax) · [EOMONTH](https://learn.microsoft.com/dax/eomonth-function-dax)
- [USERELATIONSHIP](https://learn.microsoft.com/dax/userelationship-function-dax) · [Model relationships: active vs inactive](https://learn.microsoft.com/power-bi/transform-model/desktop-relationships-understand)
- [RANKX (ties, decimal precision)](https://learn.microsoft.com/dax/rankx-function-dax)
- [SUMMARIZECOLUMNS](https://learn.microsoft.com/dax/summarizecolumns-function-dax) · [DAX query view](https://learn.microsoft.com/power-bi/transform-model/dax-query-view)
- [Specify Mark as Date Table for time intelligence](https://learn.microsoft.com/analysis-services/tabular-models/specify-mark-as-date-table-for-use-with-time-intelligence-ssas-tabular) (never use a fact table date column)
- [Power BI project semantic model folder (DAXQueries)](https://learn.microsoft.com/power-bi/developer/projects/projects-dataset)
- Blog: [Advanced DAX — Complete Guide](https://www.devladlog.com/articles/power-bi/2025-01-02-advanced-dax-complete-guide-2025/)
