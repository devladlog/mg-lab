# DEVLADLOG Deep Dive #18: IoT solution (IoT Hub and Stream Analytics)

Contoso's Porto warehouse keeps food in three cold rooms. A door left open should raise an alert in minutes. This episode builds the
pipeline: simulated cold-room sensors send telemetry to an **IoT Hub (free tier)**, a **Stream Analytics** job reads the hub's built-in
endpoint, and one query writes two outputs to blob storage: **one-minute aggregates** per room and a **COLD_ROOM_TOO_WARM alert** for a
sustained warm room. The query is tested on Microsoft's real local Stream Analytics runtime, so nothing about its logic needs a cloud job.

```
coldroom-01..03 (simulator, quota guard) ─► IoT Hub F1 (2 partitions, built-in endpoint, consumer group "asa")
                                              │ policy "service" key (the IoT Hub input has no managed identity support)
                                              ▼
                       Stream Analytics job (1 SU, compat 1.2, system-assigned identity)
                         TIMESTAMP BY observedAt · TRY_CAST · TumblingWindow(1 min) · HoppingWindow(3 min, 1 min)
                           │ aggregates                       │ alerts          (managed identity, Blob Data Contributor per container)
                           ▼                                  ▼
                     blob container "aggregates"       blob container "alerts"
```

| Path | What it is |
|---|---|
| [`asa/coldroom-telemetry.asaql`](asa/coldroom-telemetry.asaql) | The query. Deployed by Bicep (`loadTextContent`) and tested locally: the same file |
| [`asa/`](asa) (`asaproj.json`, `JobConfig.json`, `Inputs/`, `Outputs/`) | Stream Analytics project for the npm local runtime. `Inputs/local_telemetry.json` points at the committed warm-room case |
| [`src/iotlab/telemetry.py`](src/iotlab/telemetry.py) | Cold-room model, scenarios (`normal`, `door-open`, `dirty`), encoding, **free-tier quota maths and guard** |
| [`src/iotlab/simulator.py`](src/iotlab/simulator.py) | Sends telemetry with `azure-iot-device`; the client is injected so tests need no hub |
| [`src/iotlab/provision.py`](src/iotlab/provision.py) | Creates the three devices with `az iot hub device-identity` and writes connection strings to a git-ignored file (mode 0600, never printed) |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | IoT Hub F1 + consumer group, storage (shared key off, two containers), Stream Analytics job, input, two Msi outputs, scoped roles. Outputs: names only |
| [`tests/`](tests) | 50 pytest tests; `asa_cases/` holds the committed inputs and expected outputs, `asa_reference.py` an independent model of the query |

```bash
PYTHONPATH=src python3 -m iotlab sample --scenario door-open --count 3   # print messages, no network
PYTHONPATH=src python3 -m iotlab budget --minutes 20                     # 723 messages of the 8000 per day on the free tier (9%)
npx azure-streamanalytics-cicd localrun --project asa/asaproj.json --outputPath build/localrun   # run the query locally
```

## Test locally (no Azure, no tenant)

```bash
pip install -r requirements.txt
npm ci --no-audit --no-fund          # azure-streamanalytics-cicd (needs .NET SDK 8 or later on the PATH)
python3 -m pytest -q                 # 50 passed (about 70 s, most of it the local runtime starting)
```

Bicep tests need the `bicep` CLI; the query tests need the npm package and `dotnet`. Each skips with a message if its tool is missing.

What is proven, and what is not:

- **The query**, on the real runtime (`azure-streamanalytics-cicd` 4.0.3): three committed cases (steady, warm room, malformed events) match the expected
  outputs; the expected outputs also equal an independent Python model of the windows; a **mutation test** changes the threshold and the harness must fail; a
  simulator-driven door-open run alerts for `coldroom-02` only; `localrun` with the project's own input mock reproduces the committed alert file; and
  `build --v2` turns the project into an ARM template.
- **The Bicep** compiles and lints clean, and tests compare it with the query, the project files and the simulator: same input and output aliases, same job settings,
  the deployed query is the tested file, the alert threshold equals the simulator constant, blob outputs use `Msi`, storage has no shared key, roles are scoped to the
  two containers, no secret is output.
- **Not proven offline:** that IoT Hub, the job, the roles and the outputs deploy and work together; time policies (see below); the Power BI output; throughput.
  See "Not verified".

## Deploy and run (needs the lab Azure subscription)

Runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```bash
az group create -n rg-mglab-deep-dive-18 -l westeurope
az deployment group create -g rg-mglab-deep-dive-18 -n main -f infra/main.bicep -p infra/main.bicepparam \
   -p operatorObjectId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs -o json
PYTHONPATH=src python3 -m iotlab provision --hub <hubName>
az stream-analytics job start -g rg-mglab-deep-dive-18 -n <jobName> --output-start-mode JobStartTime
PYTHONPATH=src python3 -m iotlab simulate --scenario door-open --minutes 10
```

## What we learned / gotchas

- **IoT Hub input: no managed identity.** Learn (managed identities for Stream Analytics): the IoT Hub input is "No" for both identity types, with a workaround of
  routing events to Event Hubs. This job therefore needs the hub's `service` shared access policy key; the Bicep reads it with `hub.listKeys()` inside the template and
  never outputs it. The Blob outputs do use the job's system-assigned identity (Storage Blob Data Contributor on each container).
- **One consumer group per job** (Learn: IoT Hub reader limits per partition): the Bicep creates `asa` on the built-in endpoint.
- **An empty partition delays output.** The free hub has two partitions. Learn (event ordering): Stream Analytics emits output for time t only when all combined partitions
  reached t, and a partition that receives nothing holds output back by the late-arrival tolerance (`InputPartitionNotProgressing`). With three devices hashed over two partitions,
  one partition can stay empty. The job's late arrival is 60 s, so the worst case here is about a minute of extra delay. Learn's fixes: make sure every partition receives data,
  or partition the job (for compatibility level 1.2 and above Learn's parallelization page says to set the partition key as an input property; the event-ordering page shows `PARTITION BY PartitionId`).
  Not reproduced in this lab; check the Watermark Delay metric split by Partition ID.
- **Late arrival and out of order settings cost latency.** Defaults are 5 s late arrival and 0 s out of order; this job uses 60 s and 5 s (adjust). Out-of-order tolerance
  above zero delays the first output. The local runtime says "Time policy for stream analytics job is not supported for local static input file", so **these settings are not exercised by the tests**.
- **Windows are `(start, end]`.** An event exactly on the minute belongs to the window ending at it. Test fixtures are built around that.
- **Future events are clamped locally.** The local runtime moved events more than five minutes in the future to "now plus five minutes": the fixtures use past dates (2026-11-20).
- **Floating-point sums differ in the last digits** between runtimes (Learn says so too): `avgTempC` is compared with a tolerance, not exactly.
- **Free tier.** Learn: one free hub per subscription, 500 devices, 8,000 messages per day, metered in 0.5 KB chunks on a free hub (4 KB on others). A free hub cannot be upgraded.
  The simulator computes the cost of a run and refuses anything over 80 % of the day (the quota already used today is passed with `--sent-today`).
- **Stream Analytics bills while it runs.** The job is Standard, 1 streaming unit, billed per hour (check the pricing page): stop it after every recording. The free hub and the storage account cost next to nothing.
- **Local tooling.** `azure-streamanalytics-cicd build --type Bicep` failed here ("use .NET 6.0"), so the Bicep is hand-written and the project is only built to ARM (`--v2`). Project data source types are `IoT Hub` and `Blob Storage`.

## Not verified (needs the lab or a tenant)

- The deployment itself, and in particular the `filter(hub.listKeys().value, ...)[0].primaryKey` expression in the input (compiles, not run).
- Role propagation: the Msi blob outputs may fail their first validation until the role assignments apply (Learn says role changes can take minutes).
- The IoT Hub input with a free hub, the `asa` consumer group, and the job starting from `JobStartTime`.
- Real delays: the time from the door-open reading to the first alert line (window plus the 60 s late-arrival wait) and the empty-partition behaviour. The narration of the screen scenes must be corrected after the recording.
- The simulator against a real hub (`azure-iot-device` 2.14.0): the SDK path was never connected; the tests use an injected client.
- Power BI as an extra output (Learn: supported with the system-assigned identity): not built or tested here, so it is not in the episode.

## References

- [Azure IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) and [Choose the right IoT Hub tier and size](https://learn.microsoft.com/azure/iot-hub/iot-hub-scaling)
- [Azure IoT Hub billing information](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-pricing)
- [Stream data as input into Stream Analytics](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-define-inputs) and [Troubleshoot input connections](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-troubleshoot-input)
- [Managed identities for Azure Stream Analytics](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-managed-identities-overview)
- [Outputs from Azure Stream Analytics](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-define-outputs)
- [Configuring event ordering policies](https://learn.microsoft.com/azure/stream-analytics/event-ordering) and [Understand time handling](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-time-handling)
- [Use query parallelization](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-parallelization)
- [Quickstart: Create a Stream Analytics job in the Azure portal](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-quick-create-portal) and [Stream Analytics CI/CD overview](https://learn.microsoft.com/azure/stream-analytics/cicd-overview)
- [`az iot hub device-identity`](https://learn.microsoft.com/cli/azure/iot/hub/device-identity) and [`az stream-analytics job`](https://learn.microsoft.com/cli/azure/stream-analytics/job)
- Complete Guide on the blog: [IoT solution: Azure IoT Hub, Stream Analytics, real-time dashboards](https://www.devladlog.com/articles/deep-dive/2025-12-01-iot-solution-azure-iot-hub-stream-analytics-real-time-dashboards/)
