# DEVLADLOG Dynamics 365 #10 — Reporting & Analytics

The reporting layers of the sales story from [episode 7](../07-dynamics-365-sales/): the pipeline of open opportunities.
The app gives you views, charts and dashboards; Power BI connects through the Dataverse connector. **reportkit**, a small
Python tool, covers what sits between them, the part where numbers quietly disagree:

- **queries**: prints the FetchXML aggregate, the OData `$apply` query and the FetchXML month grouping it uses
- **pipeline / monthly**: open opportunities (state 0) by forecast category, or by estimated close month: count and
  estimated value; `--csv` writes the table for Excel or Power BI
- **reconcile**: the same totals computed from the rows themselves (reference), from the FetchXML aggregate and from
  OData `$apply`, group by group to the cent; the month report is checked FetchXML against the rows. Exit code 1 on a
  disagreement. The `AggregateQueryRecordLimit` error is recognised and explained
- **chart**: builds a **user chart** (`userqueryvisualization`) from a data description and a presentation description,
  validates it first (well-formed XML, every `<measure>` is a fetch alias, one `<Series>` per `<measurecollection>`,
  aggregate and group by present, name length), dry run by default, finds an existing chart by name

| Path | What it is |
|---|---|
| [`src/reportkit/queries.py`](src/reportkit/queries.py) | The three ways of asking, result normalisers, group comparison, limit-error detection |
| [`src/reportkit/reports.py`](src/reportkit/reports.py) | Report table, CSV, `reconcile` |
| [`src/reportkit/charts.py`](src/reportkit/charts.py) | Chart definitions (Learn's column and multi-series samples, adapted), validation, create |
| [`src/reportkit/cli.py`](src/reportkit/cli.py), [`webapi.py`](src/reportkit/webapi.py), [`auth.py`](src/reportkit/auth.py) | CLI; Web API client (429 + Retry-After, formatted-value annotations); MSAL token provider, as in episodes 1-9 |
| [`sample/open-opportunities.json`](sample/open-opportunities.json) | 14 fictional open opportunities (a copy of episode 7's), for the offline `pipeline` / `monthly` |
| [`tests/`](tests/) | 23 pytest tests; the Web API is a recording stub that answers from the sample rows, computed independently of the code (tests only: the demo runs against the real environment) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/10-reporting-analytics
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                              # 23 passed
cd src
python3 -m reportkit pipeline --from-json ../sample/open-opportunities.json
python3 -m reportkit monthly --from-json ../sample/open-opportunities.json
python3 -m reportkit queries
```
```
forecast category             open   estimated value
Pipeline                         7        435,000.00
Best case                        3        200,000.00
Committed                        4        118,500.00
total                           14        753,500.00
```
Offline there is nothing to reconcile: the JSON file is the "rows" method only.

## Against an environment (needs tenant)

Prerequisites: the lab's *Sales trial* environment with the sample opportunities ([demo.md](demo.md)); an identity that
can read opportunities and create charts (any user can create their own chart; `labadmin` is used).

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m reportkit pipeline
python3 -m reportkit monthly
python3 -m reportkit reconcile          # exit 1 if FetchXML / $apply disagree with the rows
python3 -m reportkit chart pipeline            # dry run
python3 -m reportkit chart pipeline --apply
```

## What we learned / gotchas

- **50,000-record limit on aggregates.** Learn (*Aggregate data by using FetchXML / OData*): aggregate queries are
  limited to 50,000 records, error `-2147164125` / `8004E023` *AggregateQueryRecordLimit exceeded*; add filters (a
  date range or a subset of a choice column) and combine several runs. FetchXML also has `aggregatelimit` for a lower per-query
  limit (not available in OData); with it the query doesn't fail, it aggregates over at most limit + 1 arbitrary rows,
  so it isn't a report you can trust. `reportkit` turns the error into that advice.
- **OData can't do everything FetchXML can.** Learn: `groupby` with datetime values isn't supported, `$orderby` with
  aggregate values isn't supported, grouping by parts of a date always uses UTC, no distinct `CountColumn`. So the monthly
  report is FetchXML (`dategrouping`).
- **Time zone in date grouping.** In FetchXML the default is the user's time zone; `usertimezone="false"` uses UTC. The
  month query sets it explicitly. `estimatedclosedate` is a date-only column, so the rows method buckets the date text.
- **Nulls.** Aggregate calculations exclude null values (Learn): a group whose values are all null has no sum, which
  the tool reads as 0, and a record with no close date forms its own `(none)` group.
- **Grouping needs an order on the alias** (Learn, *Grouping*); every attribute needs an alias; count counts rows,
  countcolumn counts rows with data.
- **Charts are two XML strings.** Data description (`<fetchcollection>` FetchXML aggregate + `<categorycollection>`) and
  presentation description (Microsoft Chart Controls `Chart` serialization, no schema); a multi-series chart has one
  `<measurecollection>` and one `<Series>` per series (Learn, *Understand charts*, *Sample charts*). Chart name max 100
  characters; a user chart's `charttype` 0 is *ASP.NET Charts*, 1 is *Power BI* (Learn, *User Chart table reference*).
  Charts with custom colors need `CustomColorOverride="true"` in the modern refreshed look (not used here).
- **Power BI.** The Dataverse connector uses the TDS endpoint (setting *Enable TDS endpoint*, on by default); ports 1433
  or 5558 must be open; most proxies don't handle TDS; result sets over 80 MB fail (*Return records size can't exceed
  83886080*), each query has a fixed five-minute timeout, and rows come at roughly 500 per second. For bulk extraction
  Learn recommends Azure Synapse Link (Learn, *Create a Power BI report using data from Dataverse*, *Dataverse connector*).
- **Not verified on Learn, so the demo confirms it** ([demo.md](demo.md) step 3): that one `aggregate(...)` can hold two
  expressions (`estimatedvalue with sum as total,$count as n`; Learn shows them in separate examples); that the FetchXML
  group-by alias carries the `FormattedValue` annotation for a choice column (the tool falls back to the number);
  that `msdyn_forecastcategory` (Sales Premium/Enterprise) exists in the environment (`--by statuscode` otherwise);
  that the `OData-EntityId` header on a create returns the chart id; and where a user chart shows in Sales Hub. If the
  real environment differs, the code and tests are fixed from its output.
- **Not built:** Excel templates and exports, dashboards (system dashboards are solution components with their own XML),
  Azure Synapse Link / Fabric Link setup (needs Azure resources and a paid capacity decision), and TDS queries from
  SQL tools: nothing here could be run for real in this build, so they stay in the blog guide, not in the episode.

## References
- [Aggregate data by using FetchXML](https://learn.microsoft.com/power-apps/developer/data-platform/fetchxml/aggregate-data) (aliases, group by, `dategrouping`, `usertimezone`, 50,000 limit, `aggregatelimit`)
- [Aggregate data by using OData](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/aggregate-data) (`$apply`, limitations)
- [Understand charts: underlying data and chart representation](https://learn.microsoft.com/power-apps/developer/model-driven-apps/understand-charts-underlying-data-chart-representation) and [Sample charts](https://learn.microsoft.com/power-apps/developer/model-driven-apps/sample-charts)
- [User Chart (UserQueryVisualization) table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/userqueryvisualization) and [System Chart (SavedQueryVisualization)](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/savedqueryvisualization)
- [Create a Power BI report using data from Dataverse](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-powerbi-connector), [Dataverse connector](https://learn.microsoft.com/power-query/connectors/dataverse), [Use Power BI with Dataverse data](https://learn.microsoft.com/power-apps/maker/data-platform/use-powerbi-dataverse), [Control access of the TDS endpoint](https://learn.microsoft.com/power-platform/admin/control-tds-settings)
- Blog: [Reporting & Analytics — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-17-reporting-analytics-complete-guide-2025/)
