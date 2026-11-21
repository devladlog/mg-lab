# DEVLADLOG AI #13 — Computer vision and image analysis: read the asset tag, blur the people

Blog guide: [Computer Vision: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-03-04-computer-vision-complete-guide-2025/)

Episode 10 sent screenshots to a vision-capable language model. The Contoso Porto service desk also receives **photos**
of equipment: a laptop with an asset sticker, a broken monitor, a meeting-room display, sometimes a colleague in the
frame. This episode uses the dedicated **Azure Vision Image Analysis 4.0** service (caption, tags, objects, read/OCR,
people, smart crops in one synchronous call), keyless from Python, for two jobs: **read the asset tag** (`CON-` and five
digits) and **never store a person**: every detected person is pixelated and the thumbnail is cut from the pixelated copy.

```
photo ──► limits.py (formats, < 20 MB, 50 < side < 16,000) ──► prepare.py (rotate, drop EXIF/GPS, ≤ 2048 px, < 6 MB, PNG)
                                                                  │
                                                  azure_backend.py: ONE analyze call (caption, tags, objects, read, people, smart crops)
                                                                  ▼                       (Azure types stop here; model.py is ours)
                    assettag.py (pattern, confidence floor, look-alike letters)      privacy.py (pixelate people ≥ 0.20, thumbnail from the copy)
                                                                  ▼
                       decide.py: attach-to-asset / attach-then-review / confirm-tag / manual-review, each with a reason
                                                                  ▼
                 out/<id>.redacted.png · .thumb.png · .json   (the original is never written)      evaluate.py: gate, exit 0 / 1
```

| Question | Answer in this episode |
|---|---|
| What can be sent? | `limits.py`, from Learn: JPEG, PNG, GIF, BMP, WEBP, ICO, TIFF, MPO; less than 20 MB; each side more than 50 and less than 16,000 px. Learn's FAQ: the client libraries handle files up to 6 MB, one image per call. `prepare.py` keeps what we send under 6 MB |
| What leaks in a phone photo? | EXIF (camera, time, GPS) is dropped by re-encoding, after the camera rotation is applied. The tests plant fictional EXIF and GPS and check they are gone |
| What does the service decide? | Text lines with a confidence per word, people boxes with a confidence. Nothing about *meaning*: the asset-tag pattern, the 0.80 confidence floor and the look-alike rule (`O` for `0`) are ours |
| How do we handle people? | `privacy.py`: boxes at confidence ≥ 0.20 are pixelated (block size ~ 1/12 of the box), with a 5 % margin. 0.20 is deliberately low: Learn's own example returns a clearly visible person at 0.27 |
| Does blurring make a photo safe? | No: **text is not blurred**. The Learn sample has names on a meeting-room display. If a photo has people and text, `decide.py` says so and the ticket is attached *and flagged* |
| Who may call it? | Keyless (`disableLocalAuth`), Entra ID against the custom subdomain, role Cognitive Services User |
| What if the service goes away? | Learn: Image Analysis is **deprecated and retires on 25 September 2028**. Only `azure_backend.py` imports the SDK; the rest uses `model.py` (`VisionBackend.analyze(bytes) -> Analysis`) |
| May this ship? | `evaluate.py`: no failed call, **zero wrong tags attached**, every person case really pixelated, at least 60 % of known tags read. Exit 1 otherwise |

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Vision resource (kind `ComputerVision`, West Europe, **F0** default, keys off, custom subdomain), Cognitive Services User for the developer |
| [`src/photoscan/limits.py`](src/photoscan/limits.py), [`prepare.py`](src/photoscan/prepare.py) | Documented limits; rotation, metadata removal, shrink |
| [`src/photoscan/model.py`](src/photoscan/model.py), [`azure_backend.py`](src/photoscan/azure_backend.py) | Our result types and the protocol; the only Azure SDK code |
| [`src/photoscan/assettag.py`](src/photoscan/assettag.py), [`privacy.py`](src/photoscan/privacy.py), [`decide.py`](src/photoscan/decide.py) | Tag rules, pixelation and thumbnail, next step with reasons |
| [`src/photoscan/pipeline.py`](src/photoscan/pipeline.py) | One photo in, safe outputs out; a failed call routes to a person; `Paced` stays under 20 calls a minute |
| [`src/photoscan/samples.py`](src/photoscan/samples.py), [`data/cases.json`](data/cases.json) | Six fictional labels drawn with Pillow (clean, tiny text, look-alike letter, low contrast, rotated phone JPEG with GPS, no tag) and the Learn sample photo, downloaded by `fetch-sample` |
| [`src/photoscan/evaluate.py`](src/photoscan/evaluate.py), [`cli.py`](src/photoscan/cli.py) | Gate and table; `python -m photoscan limits / samples / fetch-sample / analyze / evaluate` |
| [`tests/`](tests) | 40 pytest tests |

Tested with Python 3.13, `azure-ai-vision-imageanalysis 1.0.0`, `azure-identity 1.27.0`, `pillow 12.3.0`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                                         # 40 passed
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep      # no warnings
PYTHONPATH=src python -m photoscan limits                         # no Azure call
PYTHONPATH=src python -m photoscan samples --out build/photos     # six fictional photos
```

What the tests cover: the **real SDK** sends its real request (`POST <endpoint>/computervision/imageanalysis:analyze?api-version=2023-10-01&features=…&smartcrops-aspect-ratios=…`,
body = the image bytes, `Authorization: Bearer …`, no subscription-key header) through a stand-in transport that answers in the
4.0 response shape. The answers are scripted by the tests, so they prove our plumbing, the limits, the privacy rules and the
gate, **not** the accuracy of the service:
- `test_sdk_limits_prepare.py`: request shape and Entra scope, response conversion, HTTP error propagates, Learn's input and
  smart-crop ratio limits, EXIF and GPS gone from the bytes, rotation applied first, downscale under 6 MB.
- `test_tag_privacy_decide.py`: tag pattern, look-alike letters flagged and never trusted, confidence floor, pixelation changes
  exactly the box, a 0.27 person is blurred, below-threshold people are counted, boxes clamped, pixelation leaves far fewer distinct pixels, the decision rules.
- `test_pipeline_evaluate_cli_bicep.py`: the service receives the prepared bytes, a rejected image never reaches it, a failed
  call routes to a person, the JSON summary holds no OCR text other than the asset tag, pacing, the gate passes and fails for each reason, CLI exit codes, the compiled Bicep.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-13 -l westeurope
az deployment group create -g rg-mglab-ai-13 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export PHOTOSCAN_ENDPOINT=<visionEndpoint> PYTHONPATH=src
python -m photoscan fetch-sample                                    # the Learn photo (person at a meeting-room display)
python -m photoscan analyze build/photos/label-clean.png            # one photo, step by step
python -m photoscan analyze build/photos/learn-presentation.png     # a person: pixelated copy in build/out
python -m photoscan evaluate ; echo $?                              # 0 = gate passes, 1 = it does not
az group delete -n rg-mglab-ai-13 --yes
```

Every result printed by `analyze` and `evaluate` is a real call. Nothing in this folder claims a result the service has not
produced; the numbers on screen come from the run recorded in `demo.md`.

## What we learned / gotchas

- **Learn says Image Analysis is going away.** The overview carries a deprecation notice: Image Analysis 4.0 retires on
  **25 September 2028**, after which calls fail. The migration page lists Document Intelligence (OCR), the Face API, GPT models in
  Microsoft Foundry and Content Understanding (image analysis, preview) as alternatives, and also says "plan a transition by
  September 25, 2026", which sits oddly next to 2028; read the date on the page you are using. That is why the SDK is confined to one file.
- **Captions need the right region.** Learn: Caption and Dense Captions only work in listed regions (West Europe is listed; Sweden
  Central is not). Without them use 3.2. The Bicep file deploys to West Europe.
- **One image per call.** Learn's FAQ: sending several images in one call is not available. The free tier allows 20 calls a minute
  (the FAQ says "free (S0)", which we read as the free tier), so `Paced` spaces calls 3 seconds apart; the SDK also retries 429.
- **The people feature finds boxes, not identities.** Learn says it does no face recognition or attributes. Its own example returns
  a visible person at 0.27, so a "confident enough" threshold of 0.5 would leave that person unblurred. We pixelate from 0.20.
- **Pixelate, don't just blur.** Block pixelation removes detail that a mild Gaussian blur keeps; the test checks the box ends up
  with far fewer distinct pixels. It is still not a guarantee against someone who recognises a silhouette or clothes.
- **Text survives.** The sample photo shows names on a screen. Redacting people does not touch OCR text; a name inside the picture
  would need a text rule (episode 12's PII pipeline on the OCR lines is the natural next step, not built here).
- **OCR returns what it sees, including look-alikes.** `CON-4821O` is read as printed. We correct to `CON-48210` for display but
  route the ticket to a person, because a wrong asset id attached silently is worse than a slow ticket.
- **Coordinates belong to the image you sent.** `prepare.py` rotates and shrinks first, then everything (boxes, crops) is applied
  to that prepared image. Applying them to the original would land in the wrong place.
- **Seven photos are plumbing, not accuracy.** Our drawings are cleaner than real stickers; the small-text and low-contrast cases
  exist to see the service struggle, and any outcome is the finding. The `people_min` check runs on one photo.
- **Estimating cost.** The F0 tier is free (Learn quickstarts); the paid S1 price is on the Azure pricing page, which could not be
  checked without a subscription, so none is embedded. Whether a subscription may hold only one F0 Vision resource is not something
  we verified; the Bicep file has a `skuName` parameter for that case.
- **Role.** Cognitive Services User is documented as "read and list keys" of Cognitive Services; with local auth off there are no keys
  to list. Whether a narrower built-in role covers this data action was not documented on the pages we read.

Out of scope on purpose: Custom Vision / model customization (Learn: the 4.0 customization preview was retired on 31 March 2025),
face recognition, video, and Content Understanding as a replacement (named, not built).

## References

- [What is Image Analysis?](https://learn.microsoft.com/azure/ai-services/computer-vision/overview-image-analysis) — features, deprecation notice, input requirements, region availability
- [Migrate from Image Analysis](https://learn.microsoft.com/azure/ai-services/computer-vision/migration-options) — retirement date and alternatives
- [Call the Image Analysis 4.0 Analyze API](https://learn.microsoft.com/azure/ai-services/computer-vision/how-to/call-analyze-image-40) — Python client, visual features, aspect ratios 0.75 to 1.8, gender-neutral captions
- [OCR for images (4.0)](https://learn.microsoft.com/azure/ai-services/computer-vision/concept-ocr), [People detection (4.0)](https://learn.microsoft.com/azure/ai-services/computer-vision/concept-people-detection), [Image captions (4.0)](https://learn.microsoft.com/azure/ai-services/computer-vision/concept-describe-images-40), [Smart-cropped thumbnails (4.0)](https://learn.microsoft.com/azure/ai-services/computer-vision/concept-generate-thumbnails-40)
- [Azure Vision FAQ](https://learn.microsoft.com/azure/ai-services/computer-vision/faq) — free tier 20 calls a minute, 6 MB SDK files, one image per call
- [Authenticate requests to Foundry Tools](https://learn.microsoft.com/azure/ai-services/authentication) and [Azure built-in roles for AI + machine learning](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning)
- Learn quickstart photo used in the demo: `https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png` (downloaded at run time, not committed)
- Blog: [Computer Vision: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-03-04-computer-vision-complete-guide-2025/)
