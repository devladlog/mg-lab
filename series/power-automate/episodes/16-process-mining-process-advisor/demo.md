# Demo: Process mining with a checked event log

## Lab environment

- Power Automate developer or trial environment named DEV with Dataverse, signed in as `labadmin@contoso.example` (Environment Maker).
- Process mining trial or a Premium licence. Check the trial length in your own tenant (Learn shows 30 and 90 days on different pages).
- Lab laptop with Python 3 and this episode folder. No Hyper-V VM needed, no extra cost.
- Browser: private window, org URL and environment id masked in every capture.

## Steps

1. In `src`, run `python -m pmkit doctor samples/purchase-requests-eventlog-raw.csv` and keep the output on screen (scene doctor).
2. Run `python -m pmkit clean samples/purchase-requests-eventlog-raw.csv --out fixed.csv`, then `cmp fixed.csv samples/purchase-requests-eventlog.csv` (no output means identical).
3. Run `python -m pmkit analyze samples/purchase-requests-eventlog.csv --before "Manager review" "Place order"` (scene numbers).
4. In Power Automate open Process mining > Start here. Name: Purchase requests. Choose Import data > Text/CSV > Upload file (Preview), select `purchase-requests-eventlog.csv`. Capture `screens/upload.jpg`.
5. Map columns: CaseId = Case ID, ActivityName = Activity name, StartTimestamp = Start timestamp, EndTimestamp = End timestamp, Resource = Resource, Amount = Financial per case (first event), Category = Case level attribute (first event). Capture `screens/mapping.jpg`, then Save and analyze.
6. Open the Map. Show the Performance layer (mean duration) and the Rework layer. Capture `screens/map.jpg`.
7. Open the Summary. Capture `screens/kpis.jpg` beside the terminal from step 3.

## Checks that can change the script

- Do the dashboard case, event and variant counts equal 300, 1,781 and 17? If not, say so and fix the narration.
- Do average duration and rework percentage match 227.2 h and 28.0 %? Definitions may differ; narrate what the screen shows.
- Does the label for the upload path match "Upload file (Preview)"? Rename in script.yaml if not.
- Did the file import without a time zone warning?

## Optional insert: task mining

Needs Power Automate for desktop and the TDS endpoint enabled. Record one task, analyze, show it on the map. Not run in this build; script scene "task" is Learn-only.

## Masking and tear-down

Mask org URL, environment id and user name. Afterwards delete the process "Purchase requests" and the uploaded data, and remove any trial licence assigned for the recording.
