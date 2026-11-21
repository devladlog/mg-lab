# Demo shot list — Power BI #17 Real-Time Analytics and Streaming

## Lab environment

No VM and no Azure resource. Everything runs on the **Windows recording laptop** (Power BI Desktop, Windows Terminal, browser) against the **Fabric trial capacity** of the lab tenant.

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current), Python 3.11+ with `pip install azure-eventhub`, PowerShell 7, Windows Terminal, this folder copied to `C:\MGLab\power-bi\ep17\` | free |
| Tenant | Fabric + Power BI 60-day trial (West Europe capacity, see `series/LAB.md`), workspace **`Contoso Sales (Lab)`** assigned to the trial capacity, account `labadmin` (the recording account, also the trial capacity admin) | trial, 0 EUR |
| Fabric items (created in the workspace, deleted in tear-down) | Eventhouse `ContosoLive` (with its KQL database), KQL queryset `qs-till`, Eventstream `es-till-events`, Real-Time Dashboard `Live tills`, report + semantic model `Contoso Live` | trial capacity units while they run; no billing on a trial |
| Not used | any paid capacity, any Azure subscription resource, Azure Stream Analytics, PubNub | not bought |
| Optional b-roll (not in the script) | the legacy push client, see the end of this file | free |

If a Fabric item type is missing in the workspace's **New item** list, a Fabric admin has to allow it in the tenant settings: not checked in advance.

## What was verified where

| Step | In the container | On the recording day |
|---|---|---|
| Event plan, sender batching and pacing, totals/reference numbers, push client, inventory | 82 pytest tests (README) | run against the real eventstream |
| KQL statements | parsed and analysed with `Kusto.Language`, never executed | run in the KQL queryset: results must equal the sender summary and the reference |
| TMDL model, PBIP, PBIR | static checks and Microsoft's JSON schemas | opened in Desktop, DirectQuery connection, page refresh |
| Eventstream, ingestion mapping, materialized view, dashboard, service page refresh | nothing | record, and write down the differences (section "Write down") |

## Setup (off camera, once)

1. **Workspace.** `Contoso Sales (Lab)` on the trial capacity. Sign in as `labadmin`.
2. **Eventhouse.** New item, Eventhouse `ContosoLive`. Open its KQL database (the eventhouse creates a default KQL database; if the name is not `ContosoLive`, use the name you see and set it in the Desktop parameter `KqlDatabase`).
3. **Schema.** New KQL queryset `qs-till` on that database. Run the four statements of `src/kql/01-schema.kql` **one at a time** (select the statement, Run). Check: `.show table TillEventsRaw ingestion json mappings` returns `TillEventsRawMapping`; `.show materialized-views` lists `TillEventsUnique`.
4. **Eventstream.** New item, Eventstream `es-till-events`. Add source **Custom endpoint** (name `till-sender`), **Publish**. In Live view open the source's **Details** pane, **Event Hub** tab, **SAS Key Authentication**: copy the **connection string** (primary key). Do not paste it anywhere visible.
5. **Destination.** Add destination **Eventhouse**, **Direct ingestion**, workspace `Contoso Sales (Lab)`, eventhouse `ContosoLive`, Save, connect it to the eventstream, Publish. In Live view, **Configure** on the destination: **Get data**, choose the **existing table `TillEventsRaw`**, format JSON. On **Inspect the data** check that `EventTime` is a `datetime` and that the columns equal the table (if the wizard offers the existing mapping `TillEventsRawMapping`, use it; otherwise accept its inferred mapping and write down which). Finish.
6. **Rehearsal (1 minute).** In a **PowerShell 7** terminal on the laptop (`-MaskInput` needs PowerShell 7; the environment variable lives in this window only, input hidden):
   ```powershell
   cd C:\MGLab\power-bi\ep17\src
   $env:TILLSTREAM_CONNECTION_STRING = Read-Host "Event Hub connection string" -MaskInput
   python -m tillstream send --run-id rehearsal --speed 10
   ```
   `--speed 10` plays the ten minutes in about one; EventTime values are compressed too, so the flash-sale bins do not line up with whole minutes in a rehearsal. In the queryset run `TillEventsRaw | where RunId == "rehearsal" | count`; it must be 368 rows (the number of messages the sender prints). If it is zero after two minutes, the destination was not active when the data arrived (Learn: an eventstream destination starts from "now"): start the sender again.
7. **Desktop.** Open `src/ContosoLive.pbip`. Edit parameters (Transform data): `KqlClusterUri` = the **Query URI** of the KQL database (copy it in the Fabric portal, KQL database page), `KqlDatabase` = the database name. Sign in with the organizational account when asked; storage mode stays **DirectQuery**. Load. If Desktop refuses the empty report or the project, create a new report on the same model and note it. If `TillEventsUnique` does not load as a DirectQuery table, fallback in this order: Get data, **KQL Database** (OneLake catalog), pick `TillEventsRaw`, DirectQuery, and replace the measures by dedupe-aware versions (`Orders = DISTINCTCOUNT('Till Events'[EventId])`); write the fallback down.
8. **Visuals** on page **Live tills**: cards `Sales Amount`, `Orders`, `Last Event Time`; line chart (Axis `EventTime`, Values `Orders`, Legend `Channel`); column chart `Sales Amount` by `Store`. Format pane, **Page refresh**: On, **Change detection**, measure `Last Event Time`, check every **5 seconds**.
9. **Real-Time Dashboard** `Live tills`: data source = the KQL database; tiles from `live-kpis.kql`, `sales-per-minute.kql`, `orders-per-minute-anomaly.kql`. **Manage, Refresh settings, Live refresh** on.
10. **Publish** the report to `Contoso Sales (Lab)`; in the semantic model settings set the credentials of the Azure Data Explorer source (organizational account) so the service can query it.

## Recording the live part (about 14 minutes with setup)

1. Start the terminal, the eventstream Live view and Desktop side by side. Run `python -m tillstream send --run-id demo17` **about 40 seconds before a whole minute**: it waits for the minute, then plays ten minutes of sales (flash sale in minutes 6 and 7, duplicates and late events spread over the run).
2. Capture the screens below while it runs; the sender prints its summary when it ends. Keep it on screen for the `totals` scene.
3. A second take is possible: use `--run-id demo17b` and change the run id in `totals-check.kql` (the file says where).

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `eventstream` | `screens/eventstream-live.jpg` | Eventstream Live view: custom endpoint to Eventhouse, the Data preview with rows arriving; terminal inset showing the send command (connection string hidden, never printed) and, at the end, the summary (messages, batches, unique EventId, duplicates sent, late events, amount) |
| `totals` | `screens/kql-totals.jpg` | KQL queryset: `totals-check.kql` result equal to the sender's summary (Events and Amount, for RunId `demo17`); `duplicates.kql` (ExtraRows equals the sender's duplicates); `late-arrivals.kql` (P50, P95, LateOverTwoMinutes). `python -m tillstream expect` output on a dry run of the same seed in a second window is optional |
| `desktop` | `screens/desktop-page-refresh.jpg` | Desktop page **Live tills** with the sender running: cards and line chart moving without a click; Format, Page refresh, change detection on `Last Event Time`, 5 seconds, **show details**. One short cut with an Import-mode table to show the Page refresh card is missing (do not break the real model: use a scratch pbix) |
| `dashboard` | `screens/realtime-dashboard.jpg` | Real-Time Dashboard with live refresh on, three tiles updating without a reload; the `orders-per-minute-anomaly` tile lists the flash-sale minutes |
| `gotcha` | `screens/apr-minimum.jpg` | Service: the published report, Edit, Format, Page refresh: the allowed minimum and its message; as capacity admin, the capacity's automatic page refresh settings (Admin portal, capacity settings, Power BI workloads) if the trial capacity shows them. Set the report to 1 second first and show what the service does |

## Write down (the README's "Not verified" list)

1. Did ingestion work with the pre-created mapping, or did the wizard infer its own? Does `EventTime` arrive as `datetime` (query `TillEventsRaw | getschema`)?
2. Do `totals-check.kql` and the sender summary agree to the cent (Events, Amount)? Does `duplicates.kql` give the duplicates the sender reported?
3. What are the real P50 and P95 lag? Do the late events (3 minutes) show in `LateOverTwoMinutes`?
4. Which minutes does `series_decompose_anomalies` flag for `Online`? The two flash minutes (6 and 7 of the run)? Any others? What does the reference say (`python -m tillstream expect`)?
5. Does Desktop accept a materialized view as a DirectQuery table? Which fallback was needed?
6. Does the service report refresh every 5 seconds with change detection, and at which interval for a fixed interval? Are the page refresh minimums visible on the trial capacity, and what are they?
7. Did Desktop open `ContosoLive.pbip` without a repair prompt?

## Masking

Blur: tenant name and sign-in domain, the workspace and item IDs in every address bar, the **Query URI** of the KQL database, the eventstream's endpoint namespace (`eventstream-....servicebus.windows.net`) and the entity path, and
**the connection string and keys (never on screen: the terminal uses a masked prompt)**. Use `labadmin` or the demo users only. The data is fictional.

## Tear-down

1. Stop the sender (Ctrl+C) and close the terminal window (the connection string was only in that session's environment).
2. In the workspace delete: eventstream `es-till-events` (its endpoint keys die with it), Real-Time Dashboard `Live tills`, report and semantic model `Contoso Live`, KQL queryset `qs-till`, Eventhouse `ContosoLive` (this also deletes its KQL database and the tables).
3. Close Desktop without saving the connection credentials; remove the Azure Data Explorer entry under File, Options, Data source settings.
4. Delete `C:\MGLab\power-bi\ep17\` if it holds recorded values.
5. No Azure resource group was created; nothing else to delete.

## Optional b-roll: the legacy push model (not in the script's screens)

Only if the owner wants to show it. Needs an interactive sign-in by the recorder, never by an agent: in Windows PowerShell with the `MicrosoftPowerBIMgmt` module, `Connect-PowerBIServiceAccount`, then
`$env:PBI_ACCESS_TOKEN = Get-PowerBIAccessToken -AsString` (the client accepts the token with or without the `Bearer` prefix).
Then `python -m tillstream push --workspace-id <workspace id> --streaming-tiles` creates the semantic model `TillEventsLegacy` (push + streaming, `basicFIFO`) and posts the unique events, and
`python -m tillstream inventory` lists push, streaming and PubNub models in the workspaces the account can see. Delete the `TillEventsLegacy` semantic model afterwards. Neither command was run against the service.
