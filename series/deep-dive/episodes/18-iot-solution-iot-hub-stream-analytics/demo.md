# Demo shot list: DEVLADLOG Deep Dive #18, IoT solution (IoT Hub + Stream Analytics)

Code, test and Bicep/query scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs the Azure subscription.** Offline (container): 50 pytest tests pass (the query runs on the real Stream Analytics local runtime, the Bicep is compiled and
linted). **Not yet run against Azure:** the Bicep deployment, device provisioning, the simulator against a real hub, the running job, the outputs, the empty-partition
behaviour. Record each outcome in the README ("Not verified" lists what to check) and fix the narration if reality differs (especially every time and delay).

## Lab environment

Recorded on the **lab Windows laptop** (host): Windows Terminal with PowerShell 7 (Azure CLI, Python 3.10+), Edge for the Azure portal. **No Hyper-V VM, no
Power Platform environment and no Microsoft 365 licence is needed**; the simulator runs on the laptop. The only account used is `labadmin` (Owner on the lab subscription).

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-18`, West Europe)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| IoT Hub `iot-mgl18-<suffix>` | **F1 (free)**, 2 partitions, TLS 1.2 | free. Learn: one free hub per subscription, 8,000 messages per day. **Check first** that the subscription has no other free hub: `az iot hub list --query "[?sku.name=='F1'].{n:name,g:resourceGroup}" -o table` |
| Stream Analytics job `asa-mgl18-<suffix>` | **Standard, 1 streaming unit**, compatibility level 1.2, system-assigned identity | billed per hour **while running**: see the [pricing page](https://azure.microsoft.com/pricing/details/stream-analytics/). Start it for the recording, stop it right after |
| Storage account `stmgl18<suffix>` | StorageV2, Standard_LRS, shared key access off, containers `aggregates` and `alerts` | a few cents or less: a few small blobs ([pricing](https://azure.microsoft.com/pricing/details/storage/blobs/)) |
| 3 device identities `coldroom-01..03` | in the free hub | free (identity registry operations are not charged, Learn) |
| Role assignments (job identity: Storage Blob Data Contributor on each container; optional operator: Data Reader) | n/a | free |

No Event Hubs, no Log Analytics workspace, no Power BI output, no Defender plans. Budget alert `mglab-monthly` (EUR 30) stays active.

**Local tools on the laptop:** Azure CLI with the IoT extension (`az extension add -n azure-iot`) and the Stream Analytics extension (`az extension add -n stream-analytics`),
Python 3.10+ with `pip install -r requirements.txt` (installs `azure-iot-device`), Node 20+ with `npm ci` and .NET SDK 8+ for the local tests, Bicep CLI.

## Prerequisites

- `labadmin` signed in to the Azure CLI (off camera). Providers: `az provider register --namespace Microsoft.Devices`, `Microsoft.StreamAnalytics`, `Microsoft.Storage`.
- The first free IoT Hub in a subscription: if another group already holds the free hub, delete it or change the episode (the F1 limit is per subscription).

## Setup (off camera)

1. **Tests first**
   ```powershell
   cd series/deep-dive/episodes/18-iot-solution-iot-hub-stream-analytics
   pip install -r requirements.txt ; npm ci --no-audit --no-fund
   python -m pytest -q                       # expect 50 passed
   $env:PYTHONPATH = "src"
   python -m iotlab budget --minutes 20      # 723 messages of the 8000 per day (9%)
   ```
2. **Deploy**
   ```powershell
   az group create -n rg-mglab-deep-dive-18 -l westeurope
   $me = az ad signed-in-user show --query id -o tsv
   $o = az deployment group create -g rg-mglab-deep-dive-18 -n main -f infra/main.bicep -p infra/main.bicepparam -p operatorObjectId=$me --query properties.outputs -o json | ConvertFrom-Json
   ```
   **Check and write into the README:** (a) the deployment succeeds and how long it took (an F1 hub can take several minutes); (b) the job exists with status *Created*;
   (c) the input **Test connection** in the portal succeeds (this is the unverified `hub.listKeys()` filter); (d) both outputs **Test connection** succeed. If an output fails right
   after deployment, wait a few minutes for the role assignments (Learn: role changes can take minutes) and retest; write down how long it took.
3. **Devices** (connection strings go to `devices.local.json`, git-ignored, mode 0600, never printed)
   ```powershell
   python -m iotlab provision --hub $o.hubName.value
   ```
4. **Start the job and check partitions**
   ```powershell
   az stream-analytics job start -g rg-mglab-deep-dive-18 -n $o.jobName.value --output-start-mode JobStartTime
   ```
   Wait until the portal shows *Running*.
5. **Normal run, then the door**
   ```powershell
   python -m iotlab simulate --scenario normal --minutes 5
   python -m iotlab simulate --scenario door-open --minutes 10 --sent-today 183
   ```
   `--sent-today` is the number of messages already used today (portal: IoT Hub overview). The simulator refuses runs that would pass 80 % of 8,000. Write into the README:
   the time from the first door-open reading (tick 13, about 65 s into the run) to the first line in `alerts`; whether a partition stayed empty (Watermark Delay split by Partition ID);
   the first aggregate line's delay.
6. **Look at the output** (Storage browser in the portal, or `az storage blob list --account-name <st> -c aggregates --auth-mode login -o table`; needs the operator role from `operatorObjectId`, which may take a few minutes).
7. **Optional, dirty data:** `python -m iotlab simulate --scenario dirty --minutes 3` shows that malformed readings do not stop the job (Input deserialization/ events in the metrics).

## Screens to capture (1920x1080, browser zoom 100 %, terminal font large)

| Scene | Capture | File |
|---|---|---|
| `devices-screen` | IoT Hub overview (tier F1, daily limit), Devices list, Metrics "Telemetry messages sent" during a run | `screens/iothub.jpg` |
| `job-screen` | Stream Analytics overview *Running*; Monitoring: Input Events, Output Events, Watermark Delay by Partition ID | `screens/job.jpg` |
| `aggregates-screen` | Storage browser > aggregates > date/hour > the blob content (JSON lines) | `screens/aggregates.jpg` |
| `alert-screen` | Split: terminal running the door-open simulation, alerts blob with `COLD_ROOM_TOO_WARM` lines | `screens/alert.jpg` |

State in the narration what you actually saw (delays, partition behaviour). If both partitions receive data and no delay appears, say that the empty-partition risk is documented but did not show up.

## Masking

Run `pipeline/mask.js` before portal captures. Mask the subscription id, tenant id and name, the hub, job and storage account names (they carry a hash of the group id), the
operator's object id, and device connection strings (they are never displayed: `devices.local.json` stays off screen). No key, SAS or connection string is shown anywhere.

## Tear-down

```powershell
az stream-analytics job stop -g rg-mglab-deep-dive-18 -n $o.jobName.value      # stops billing at once, also if the group delete is delayed
az group delete -n rg-mglab-deep-dive-18 --yes
Remove-Item devices.local.json -ErrorAction SilentlyContinue                    # its connection strings are for hub devices that no longer exist
Remove-Item build -Recurse -ErrorAction SilentlyContinue
```

Everything is in the one group: hub, job, storage, role assignments (the job identity is deleted with the job). Deleting it frees the subscription's one free IoT hub.
Confirm in the portal that the group is gone. No Entra objects, licences or tenant settings are created in this episode.
