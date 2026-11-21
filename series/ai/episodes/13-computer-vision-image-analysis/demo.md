# Demo shot list — DEVLADLOG AI #13 (computer vision and image analysis)

Everything in `src/` and `infra/` is tested locally (40 pytest tests, Bicep build + lint) with the real SDK against a
stand-in transport. The four `screen` scenes **need the lab subscription**: every result on screen comes from the real Azure
Vision service. No M365 tenant objects are used. The recording shows what the service really returned; a missed tag, an
unblurred person or a failed gate is the episode, not a retake.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-13`, region **West Europe** (Learn lists it for Image Analysis 4.0 including Captions) |
| Vision resource | `mglab-vis-…`, kind `ComputerVision`, **Free F0** (Bicep parameter `skuName`), custom subdomain, keys off |
| Roles (Bicep) | `labadmin`: **Cognitive Services User** on the resource |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI, an image viewer; browser on the lab tenant for the Azure portal |

**Estimated cost for the recording window:** F0 is free (Learn quickstarts say the free tier can be used to try the service). Learn's
FAQ gives 20 calls per minute on it; a full `evaluate` is seven calls plus a few `analyze` runs, a few dozen calls even with retakes.
The monthly free allowance is not stated on the pages checked, so none is quoted. If F0 is refused or exhausted, redeploy with
`-p skuName=S1`; the S1 price is on the Azure pricing page, which could not be checked without a subscription. Delete the resource group the same day.

**Needs verification before recording (not checkable without a subscription):**
1. **F0 availability.** If the deployment is refused because the subscription already has a free Vision resource, use `skuName=S1` and say so.
2. **Role is enough?** Cognitive Services User should cover the call (allow ~5 minutes after assignment). A 401/403 means the role has not
   propagated or the endpoint is not the custom-subdomain one. Say which in the `resource-screen` TODO.
3. **Entra scope.** The SDK asks the credential for `https://cognitiveservices.azure.com/.default` (confirmed in the local tests).
4. **What the service reads.** Drawn labels are cleaner than real stickers. `label-small` (tiny text on a 3200x2200 canvas) and `label-lowcontrast`
   may well be missed; that lowers the read rate, and the gate (60 %) may fail. Do not edit `data/cases.json` or the drawings to make the table greener.
5. **The look-alike case.** `CON-4821O` should be read with a letter O; if the service returns a zero the case is "attach-to-asset", the table shows a
   decision mismatch, and that is the finding.
6. **People.** The Learn photo should return one person; the box may not cover the whole body (hands, hat). Zoom on the redacted file and say what you see.
   The names on the room display remain readable (OCR sees them); that is expected and is the point of the scene.
7. **Deprecation notice.** Re-read the notice and the date on the Learn overview page on the recording day; the migration page also contains
   a "September 25, 2026" line. Quote the date on the overview page and say that Learn is inconsistent.

## Setup (off camera)

```bash
cd series/ai/episodes/13-computer-vision-image-analysis
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                          # expect 40 passed
az login                                                           # labadmin, off camera
az group create -n rg-mglab-ai-13 -l westeurope
az deployment group create -g rg-mglab-ai-13 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai13-outputs.json     # don't show this file on camera
export PHOTOSCAN_ENDPOINT=$(jq -r .visionEndpoint.value /tmp/ai13-outputs.json)
export PYTHONPATH=src
python -m photoscan samples --out build/photos                     # six fictional photos
python -m photoscan fetch-sample                                   # the Learn photo, off camera (downloads from learn.microsoft.com)
```

Wait ~5 minutes for the role assignment. Dry run off camera: `python -m photoscan analyze build/photos/label-clean.png`.
Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user or host name). Open the PNG files in an image viewer
side by side for `room-screen`.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `analyze-screen` | `screens/analyze-label.jpg` | `python -m photoscan analyze build/photos/label-clean.png`: caption with confidence, tags, objects, text lines, people line, asset tag with confidence, decision, the "original is never written" line. |
| `room-screen` | `screens/room.jpg` | `python -m photoscan analyze build/photos/learn-presentation.png`, then `build/out/learn-presentation.redacted.png` beside `build/photos/learn-presentation.png`: person pixelated, display names still readable; the decision line with the text-and-people warning. |
| `resource-screen` | `screens/resource.jpg` | Azure portal → the Vision resource: Overview (tier, region, endpoint masked), local authentication disabled, Access control (IAM) with the Cognitive Services User assignment. Mask subscription, tenant, user and the name suffix. |
| `evaluate-screen` | `screens/evaluate.jpg` | `python -m photoscan evaluate ; echo exit=$?`: seven rows, `!` problem lines, the summary line, RESULT, exit code. |

After recording, update the TODO comments in `script.yaml` with what the service returned, including misses and a failed gate.
Keep `build/` until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). Don't `echo` `$PHOTOSCAN_ENDPOINT`;
  don't show `/tmp/ai13-outputs.json`.
- The labels are drawn by `samples.py` (`CONTOSO PORTO`, `CON-xxxxx`). The meeting-room photo is Microsoft's Learn sample; its on-screen names
  belong to that sample. Do not use any real photo of people or any real asset tag in a take.
- Don't show the pricing page or Cost Management with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-13 --yes
az cognitiveservices account purge -g rg-mglab-ai-13 -n <visionName> -l westeurope
rm -rf /tmp/ai13-outputs.json build; deactivate; rm -rf .venv
```

Purge releases the soft-deleted resource name. Confirm in Cost Management the next day that nothing in `rg-mglab-ai-13` is billing.
