# DEVLADLOG Power BI #17: Real-Time Analytics and Streaming

Same **Contoso Bikes** as episodes 1-16 (same catalog, same stores, copied from episode 1). Until now the data was a file or a nightly refresh. This
episode makes the **tills talk**: a sender streams till sales into a **Microsoft Fabric eventstream**, an **eventhouse** stores them, and Power BI reads them
**live**, in a DirectQuery report with **automatic page refresh** and in a Real-Time Dashboard. The old way (push and streaming semantic models) is built too,
as a comparison, because Learn says its creation is going away.

Blog guide: <https://www.devladlog.com/articles/power-bi/2026-06-04-real-time-analytics-complete-guide-2026/> (its code was not used and not checked).

**Draft status.** The sender, the REST client, the KQL, the inventory script and the model are written and tested here. Nothing was run against Fabric or
Power BI (no sign-in in the container): every `screen` scene is recorded on the lab tenant, see [demo.md](demo.md).

| Path | What it is |
|---|---|
| [`src/tillstream/events.py`](src/tillstream/events.py), [`catalog.py`](src/tillstream/catalog.py) | The plan of a live sales stream: deterministic for a seed, with a **flash sale**, **duplicates** and **late events** planted. `catalog.py` is a verbatim copy of the data of episode 1 (a test compares them) |
| [`src/tillstream/sender.py`](src/tillstream/sender.py) | Paced sender: Event Hubs protocol (`azure-eventhub`) to the **custom endpoint** of an eventstream, or NDJSON to a file; batching; run summary (the numbers the KQL totals must reproduce) |
| [`src/tillstream/reference.py`](src/tillstream/reference.py) | Plain-Python reference of the KQL results: totals after deduplication, orders per minute, spike minutes (median and MAD) |
| [`src/tillstream/push.py`](src/tillstream/push.py) | The **legacy** path: create a push+streaming semantic model, post rows in chunks (10,000 rows, optional 15 KB), wait on `429 Retry-After`, delete rows. Standard library only |
| [`src/tillstream/inventory.py`](src/tillstream/inventory.py) | Lists push, streaming and PubNub semantic models in the workspaces you can see (CSV): the migration inventory |
| [`src/tillstream/cli.py`](src/tillstream/cli.py) | `python -m tillstream send / push / expect / inventory`; secrets only from environment variables |
| [`src/kql/01-schema.kql`](src/kql/01-schema.kql) | Eventhouse: `TillEventsRaw` table, JSON ingestion mapping, retention, and the **deduplicating materialized view** `TillEventsUnique` |
| [`src/kql/queries/`](src/kql/queries) | Six queries: live KPIs, sales per minute, orders-per-minute anomalies (`series_decompose_anomalies`), duplicates, ingestion lag, totals check |
| [`src/KqlCheck/`](src/KqlCheck) | .NET 8 console app: parses and semantically analyses every `.kql` statement with Microsoft's `Kusto.Language` |
| [`src/ContosoLive.SemanticModel/`](src/ContosoLive.SemanticModel), [`ContosoLive.Report/`](src/ContosoLive.Report), [`ContosoLive.pbip`](src/ContosoLive.pbip) | TMDL model: **one DirectQuery table** over `TillEventsUnique` (`AzureDataExplorer.Contents`), four measures, two parameters (`KqlClusterUri`, `KqlDatabase`); an empty PBIR report with one page for the visuals built on camera |
| [`tests/`](tests) | pytest, 82 tests (below) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 890 words) and the recorder's shot list |

## Run it

```bash
# from the episode folder (needs pytest, PyYAML, jsonschema, referencing, azure-eventhub; the KQL test also needs the .NET SDK)
python3 -m pytest tests -q            # 82 passed in about 10 s

# a dry run: ten minutes of sales into a file, then what the Eventhouse should answer
cd src
python3 -m tillstream send --dry-run /tmp/run.ndjson --no-wait      # messages 368, unique 361, duplicates 7, late 5, amount 81944.30 (seed 42)
python3 -m tillstream expect /tmp/run.ndjson                        # totals, online orders per minute, spike minutes

# parse and analyse the KQL (one statement per blank-line-separated block)
dotnet run --project KqlCheck -- kql                                # 10 statements, 0 errors (then delete KqlCheck/bin and KqlCheck/obj)

# the real thing (lab tenant, see demo.md): the connection string of the eventstream custom endpoint, Event Hub tab, in an environment variable
export TILLSTREAM_CONNECTION_STRING='...EntityPath=...'
python3 -m tillstream send --run-id demo17                          # waits for the next whole minute, then ten minutes of sales
```

`send` numbers for seed 42 depend only on the seed: the dry run above prints the same summary every time (event ids are `uuid5` of the run id, seed and index).
The EventTime values depend on `t0` (the next whole minute in a live run, now in a dry run).

What the 82 tests cover:

- **Events (13):** deterministic per seed; catalog equals episode 1; every record has the KQL columns in order with consistent price, amount, store and channel; timestamps
  are ISO UTC with milliseconds; duplicates and late events are planted and are exactly what the plan says; the flash sale is a burst of online helmets (more than three times the other
  minutes); event ids depend on the run id; bad arguments are refused.
- **Sender (12):** summary counts equal the plan and equal what a reference computes from the payloads; pacing never sends early, waits for the start delay, and `speed` compresses time;
  `next_minute`; NDJSON round trip; the Event Hubs transport splits a full batch with the real `azure.eventhub.EventData` class and a fake producer, and builds the real client from a
  connection string without connecting.
- **Push client (13):** the create body follows the documented shape and limits; chunking by rows and by bytes (15 KB); URLs, methods and bearer header against a **real HTTP server on an ephemeral
  port**; `429` waits the `Retry-After` value then succeeds; gives up after the retries; other errors carry status and body; paces itself at 120 requests a minute; a pasted `Bearer ...` value is accepted.
- **Inventory (4), reference (7), CLI (5):** classification of push, streaming, PubNub and read-only results; CSV; totals, deduplication and spike detection (flat series gives none); dry run then `expect`; missing
  secrets are explained and secrets are never command-line arguments.
- **KQL (8):** all ten statements pass `Kusto.Language` (one test); the checker really fails on a mistyped command and on a missing column; table columns and mapping equal the event fields and types;
  the view follows Learn's deduplication example; dashboard queries read the view and only the diagnostics read the raw table; one statement per query file.
- **Model (15) and script (5):** DirectQuery partition, columns and types equal the event fields, measures reference real columns, parameters hold placeholders, TMDL uses tabs, the `.pbip`, `.pbism`, `.pbir` and all PBIR
  files validate against Microsoft's published JSON schemas (vendored in `tests/schemas`); `script.yaml` follows the series brief and every code scene is a real excerpt of `src/`.

## Needs tenant / Desktop / licence

- **Lab tenant + Fabric trial capacity** (workspace `Contoso Sales (Lab)`): everything that is not Python or parsing: the eventstream, the eventhouse and its ingestion, running the KQL, the Real-Time Dashboard, publishing the report,
  page refresh in the service, the capacity's page refresh minimum.
- **Power BI Desktop (Windows laptop) + the tenant:** the DirectQuery report on the KQL database (sign-in to the source), automatic page refresh, change detection.
- **No Azure subscription resource and no paid capacity.** The legacy push client is exercised only against a local HTTP server in the tests; running it for real is optional b-roll and needs an interactive sign-in by the recorder.

## Not verified / not done

1. **Nothing ran against the real services.** The Event Hubs send, the eventstream-to-eventhouse ingestion with the pre-created mapping, the materialized view, the queries, the Desktop connection and the page refresh are untested. The KQL is only parsed and analysed (`Kusto.Language`), never executed: there is no Kusto engine in the container.
2. **The KQL anomaly query** is checked for syntax and types only. Whether `series_decompose_anomalies(Orders, 2.5, 0, 'avg')` flags exactly the two flash minutes (as the median-and-MAD reference does) is for the recording.
3. **Eventstream wizard details.** Whether the Eventhouse "Get data" screen offers the pre-created mapping `TillEventsRawMapping` or builds its own is not documented in what I read; demo.md says what to check (`EventTime` must be a `datetime`).
4. **Whether the Navigator and `AzureDataExplorer.Contents(..., "TillEventsUnique", [])` accept a materialized view** in DirectQuery is not documented in what I read. The connector documents a table name or a query as the third argument. demo.md has a fallback (a KQL function, or the table plus a dedupe measure).
5. **The DAX and the TMDL** were never opened in Desktop or evaluated (there is no DAX engine); the empty report uses `"themeCollection": {}` as in episode 16 and is only schema-valid. The page refresh settings are **not** in the PBIR: they are set in Desktop on camera, because the page schema leaves their shape open.
6. **Trial capacity and page refresh settings.** Learn describes the capacity admin's minimum interval and execution interval, but I could not verify they are exposed on a Fabric trial capacity; the gotcha screen records what the lab really shows.
7. **Pure streaming models in the inventory:** `GET datasets` may not return them (Learn lists `RealTimeInStreamingMode` as a content provider type but does not say the list includes them). The inventory reports what the API returns, and the script says it is a floor.
8. **Fabric capacity consumption** of an eventstream and an eventhouse is not estimated here (Learn has separate consumption pages); on a trial the recording costs nothing, but a production sizing needs those pages.
9. The blog guide's code and claims were not used and not checked.

## What we learned / gotchas

- **Real-time streaming in Power BI is being retired.** Learn: creation of streaming models (push, streaming, PubNub, streaming tiles) stays enabled until **31 October 2027**; after that no new ones can be created, existing ones are unaffected; Learn recommends Real-Time Intelligence in Fabric.
- **Push semantic model limits** (Learn): 75 columns and 75 tables, **10,000 rows per POST**, **1,000,000 rows per hour**, 5 pending POSTs, **120 POSTs per minute**, 250,000-row tables limited to 120 POSTs per hour, 200,000 rows kept in a FIFO model, 5,000,000 in a "none" retention model, 4,000 characters per string value. A **streaming tile** takes **15 KB per request**; Azure Stream Analytics output (push+streaming with `basicFIFO`) starts batching if it writes once or twice a second and can break the tiles.
- **Automatic page refresh needs DirectQuery.** In Import mode the Page refresh card is not shown. Desktop has no minimum (one second is allowed); the **service** does: shared workspaces 30 minutes and no change detection, dedicated capacities as the admin sets (defaults: **five minutes** fixed interval, **five seconds** change detection execution), and the service overrides a lower interval. An admin override can only raise an interval.
- **Change detection** polls one measure (count, count distinct, min, max or sum, or your own), one per model, evaluated with the author's credentials; service principals are not supported; if the measure never changes, nothing refreshes. APR queries bypass the cache and run at low priority, and a query slower than the interval delays the next one.
- **Push models and APR:** Learn's table lists push semantic models with a minimum of **30 minutes** and no change detection; streaming semantic models do not support APR at all.
- **Custom endpoint** of an eventstream speaks the **Event Hubs, AMQP and Kafka** protocols; the Event Hub tab's connection string contains `EntityPath`, so `EventHubProducerClient.from_connection_string(conn)` needs nothing else. The workspace must be on Fabric capacity or trial.
- **Duplicates are the sender's business, so the sender here makes some on purpose** (a producer that retries after a timeout sends twice). Learn's materialized-view deduplication (`take_any(*) by EventId`) only deduplicates **against records ingested within the lookback** (default relative to ingestion time); a later duplicate gets through.
- **An eventstream destination started "from now"** can miss rows ingested before routing was ready (Learn's note on CDC snapshots); start the sender after the eventstream is published and the destination shows as active.
- **Hit while building:** `pytest.approx` refuses a `timedelta` without an explicit tolerance; `azure-eventhub` raises `ValueError` from `EventDataBatch.add` when the batch is full (the sender catches that).

## References (Microsoft Learn)

- Real-time streaming in Power BI (retirement notice, model types, limits): <https://learn.microsoft.com/en-us/power-bi/connect-data/service-real-time-streaming>
- Push semantic model limitations: <https://learn.microsoft.com/en-us/power-bi/developer/embedded/push-datasets-limitations>
- REST: Datasets PostDatasetInGroup: <https://learn.microsoft.com/en-us/rest/api/power-bi/push-datasets/datasets-post-dataset-in-group>
- REST: Datasets PostRowsInGroup: <https://learn.microsoft.com/en-us/rest/api/power-bi/push-datasets/datasets-post-rows-in-group>
- REST: Datasets DeleteRowsInGroup: <https://learn.microsoft.com/en-us/rest/api/power-bi/push-datasets/datasets-delete-rows-in-group>
- REST: Datasets DeleteDatasetInGroup: <https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/delete-dataset-in-group>
- REST: Datasets GetDatasetsInGroup: <https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasets-in-group>
- REST: Groups GetGroups: <https://learn.microsoft.com/en-us/rest/api/power-bi/groups/get-groups>
- Throttling (429 and `Retry-After`): <https://learn.microsoft.com/en-us/power-bi/developer/automation/api-rest-api-limitations>
- Automatic page refresh: <https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-automatic-page-refresh>
- What is Real-Time Intelligence: <https://learn.microsoft.com/en-us/fabric/real-time-intelligence/overview>
- Eventstream custom endpoint source: <https://learn.microsoft.com/en-us/fabric/real-time-intelligence/event-streams/add-source-custom-app>
- Eventstream Eventhouse destination (direct ingestion): <https://learn.microsoft.com/en-us/fabric/real-time-intelligence/event-streams/add-destination-kql-database>
- Connect a KQL database to Power BI Desktop (Import and DirectQuery): <https://learn.microsoft.com/en-us/fabric/real-time-intelligence/power-bi-data-connector>
- Azure Data Explorer connector (`AzureDataExplorer.Contents`): <https://learn.microsoft.com/en-us/power-query/connectors/azure-data-explorer>
- Real-Time Dashboard (live refresh): <https://learn.microsoft.com/en-us/fabric/real-time-intelligence/dashboard-real-time-create>
- Materialized views, deduplication use case: <https://learn.microsoft.com/en-us/kusto/management/materialized-views/materialized-view-use-cases?view=microsoft-fabric>
- `.create materialized-view`: <https://learn.microsoft.com/en-us/kusto/management/materialized-views/materialized-view-create?view=microsoft-fabric>
- `.create-or-alter` ingestion mapping and JSON mapping: <https://learn.microsoft.com/en-us/kusto/management/create-or-alter-ingestion-mapping-command?view=microsoft-fabric>, <https://learn.microsoft.com/en-us/kusto/management/json-mapping?view=microsoft-fabric>
- `series_decompose_anomalies()`: <https://learn.microsoft.com/en-us/kusto/query/series-decompose-anomalies-function?view=microsoft-fabric>
- Blog Complete Guide: <https://www.devladlog.com/articles/power-bi/2026-06-04-real-time-analytics-complete-guide-2026/>
