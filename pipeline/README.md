# MG Lab video pipeline

Turns an episode `script.yaml` into:

- `mglab-epNN-<slug>.mp4` — 1080p narrated episode with slides, code highlighting and background music
- `mglab-epNN-<slug>.srt` — captions to upload to YouTube
- `mglab-epNN-<slug>-chapters.txt` — paste into the YouTube description
- `mglab-epNN-<slug>-thumbnail.jpg` — 1280×720
- `mglab-epNN-<slug>-short-<id>.mp4` — 1080×1920 Shorts (one per scene marked `short:`), captions burned in

## Setup (once)

```powershell
winget install Gyan.FFmpeg            # or any ffmpeg on PATH
python -m pip install -r requirements.txt
mkdir models
# download into ./models from https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0):
#   kokoro-v1.0.onnx, voices-v1.0.bin
```

Put brand assets in `./assets`:
- `background.png` — galaxy keyframe (included)
- `music.mp3` — licensed instrumental track (optional, not in git)

## Run

```powershell
python make_episode.py ..\episodes\01-power-platform-alm\script.yaml --out .\build\ep01
python make_episode.py ..\episodes\01-power-platform-alm\script.yaml --out .\build\ep01 --only-shorts
python make_episode.py <script> --voice bm_george   # British male voice
```

Narration is cached per scene (`build/.../work/*.wav`): delete a scene's `.wav` to regenerate only that scene.

## Script format

```yaml
episode: 2
slug: power-automate-error-handling
title: "..."
voice: am_michael
scenes:
  - id: hook
    type: title | bullets | code | diagram | outro
    heading: "..."
    bullets: [...]            # bullets
    code: |                   # code
      ...
    lang: yaml                # any Pygments lexer
    nodes: [...]              # diagram
    labels: [...]
    short: hook               # optional: also render this scene as a Short
    narration: >
      What the voice says.
```

## Using your own voice

Record each scene as `work/NN_<id>.wav` (48 kHz mono) with the same names the pipeline generates;
the pipeline uses existing WAVs instead of synthesising.
