# Episode 16: Process mining and task mining (series: Power Automate)

Companion code for the DEVLADLOG video. Blog guide: https://www.devladlog.com/articles/power-automate/2026-03-31-process-mining-complete-guide-2026/

Scenario: the fictional Contoso purchasing team. 300 purchase requests, one event per activity. The product does the mining; this episode builds what you need around it: a realistic event log, a checker that finds the errors the upload would trip over, a cleaner, and a local analysis you can compare against the dashboard.

Status: all code and sample data run and are tested locally. The Power Automate screens (upload, mapping, map, KPIs) need a tenant and are not recorded or verified yet (see below).

## Files

| Path | What it is |
|---|---|
| `src/pmkit/eventlog.py` | Column set, mapping to process mining attribute types, strict CSV writer and reader (UTF-8, CRLF, no BOM) |
| `src/pmkit/generate.py` | Deterministic generator (seed 26): purchasing log with rework, self-loops, rejections, maverick orders, working-hours timing |
| `src/pmkit/validate.py` | `doctor` rules PM001 to PM010 and the `clean` repair |
| `src/pmkit/analyze.py` | Variants, durations, self-loop/loop/rework percentages, activity stats, transition waits, precedence check |
| `src/samples/purchase-requests-eventlog.csv` | Clean log: 300 cases, 1,781 events |
| `src/samples/purchase-requests-eventlog-raw.csv` | Same log with planted defects |
| `tests/` | 31 pytest tests |
| `script.yaml`, `demo.md` | Video script and lab steps |

## Run it

```
cd src
python -m pmkit generate --out samples/purchase-requests-eventlog.csv
python -m pmkit doctor samples/purchase-requests-eventlog-raw.csv
python -m pmkit clean samples/purchase-requests-eventlog-raw.csv --out fixed.csv
python -m pmkit analyze samples/purchase-requests-eventlog.csv --before "Manager review" "Place order"
```

Tests (from the episode folder):

```
python -m pytest
```

Result on the build machine: 31 passed in about 5 s. Needs Python 3 and pytest only; no network, no tenant.

## What the local numbers say

- 300 cases, 1,781 events, 9 activities, 17 variants, 6 resources.
- Average case duration 227.2 h (about 9.5 days), median 234.1 h.
- Self-loop 7.7 %, loop 22.3 %, rework 28.0 % of cases.
- Slowest mean transition wait: Place order to Receive goods, 155.6 h (supplier delivery). Slowest one the team owns: Manager review to Finance review, 64.7 h over 106 cases.
- 8 cases placed the order before the manager review.
- Cleaning the raw file reproduces the clean file byte for byte (tested).

The transition wait here is our own definition (next start minus previous end). The product's performance layer may define durations differently, so compare, do not assume equal.

## Gotchas (from Microsoft Learn)

1. Case ID, Activity name and Start timestamp are the minimum; the Case ID must be on every row. Use one consistent timestamp format (ISO 8601 recommended).
2. Each activity spelling becomes its own node on the map. The doctor flags case and spacing variants (PM005).
3. Limits: the trial includes 100 MB of process data per process; each Premium licence adds 50 MB to the tenant pool. Learn gives different trial lengths on different pages (30 and 90 days), so check your own tenant.
4. The Dataverse connector and Dataflow are not supported as sources for process mining. Use the OData connector with a URL ending in `api/data/v9.2`.
5. Most tables hold current state, not history. For Dynamics 365 the activity history sits in the Activities table.
6. Some KPIs need a Premium licence and your own Power BI workspace.
7. Learn page addresses still say `process-advisor` while the pages say process mining and task mining.
8. Task mining needs the TDS endpoint enabled and uses recordings from Power Automate for desktop.

## What was not verified here

- Everything in the Power Automate UI: the upload path (Upload file (Preview) versus OneDrive), the mapping screen labels, the map layers, the summary KPIs. The script and demo are written from Learn and must be checked against the real screens.
- How the dashboard defines transition duration, loop and rework percentages. Our numbers may differ; if so, the script narration must follow the dashboard and say so.
- The trial length conflict and the exact licence pool in your tenant.
- Whether the product accepts the CRLF CSV and the timestamp format with no time zone as written. The format follows Learn but has not been uploaded.
- Task mining (recorder, analysis, Automate activities): described from Learn only, nothing run.

## Microsoft Learn references

- https://learn.microsoft.com/en-us/power-automate/process-mining-processes-and-data
- https://learn.microsoft.com/en-us/power-automate/process-mining-tutorial
- https://learn.microsoft.com/en-us/power-automate/process-mining-transform
- https://learn.microsoft.com/en-us/power-automate/process-mining-visualize
- https://learn.microsoft.com/en-us/power-automate/process-advisor-overview
- https://learn.microsoft.com/en-us/power-automate/task-mining-overview
- https://learn.microsoft.com/en-us/power-automate/process-advisor-analyze
- https://learn.microsoft.com/en-us/power-automate/process-mining-byo-azure-data-lake
- https://learn.microsoft.com/en-us/power-automate/process-mining-files-fabric-onelake
- https://learn.microsoft.com/en-us/power-automate/object-centric-create-event-log
- https://learn.microsoft.com/en-us/power-platform/admin/powerapps-flow-licensing-faq
