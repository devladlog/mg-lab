# Demo shot list - Copilot & AI #23 Local LLMs on Your Own GPU

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used: the point is the model runs on the recording laptop's own GPU |
| Tenant / accounts / licences | **None.** No Microsoft 365, Azure or API account; nothing is signed in. Cost: EUR 0 (model downloads use disk and bandwidth only) |
| Recording machine | The lab Windows laptop (host), the one with the NVIDIA GPU (series plan: RTX 5090, 192 GB RAM). Windows Terminal (dark, 18 pt) in the repo folder, Python 3.10+ on PATH |
| Software already on the laptop | Ollama and LM Studio (series plan says both are installed): check both open from the terminal/Start menu. **To install for the optional Foundry Local screen:** `winget install Microsoft.FoundryLocal` (Learn: Windows, CLI is preview), then reopen the terminal and run `foundry --version` |
| Models | 2 or 3 from the Ollama library, chosen **on the day** from `ollama list` / ollama.com/library: one small (about 8B parameters or less) and one that is too big for the GPU (to show the "does not fit" and the CPU spill). Check each model's size and licence on its library page first; note both here before recording: `__________` |
| Disk | Enough for the models (the sizes are on each library page; not verified here). Ollama's folder can be on any drive |

## What was verified where

| Step | Build container (Linux) | Needs the laptop |
|---|---|---|
| Clients, sizing maths, bench, extract, CLI | yes: 33 pytest tests against a scripted HTTP stand-in (tests only) | - |
| Real Ollama / LM Studio / Foundry Local responses | no | **first real run** |
| Real VRAM, tokens per second, GPU placement | no | **record them** |

Open points that change the script: (1) the exact GPU and its memory (`nvidia-smi`): NVIDIA lists the RTX 5090 *Laptop* GPU with
24 GB GDDR7, so say whatever the machine reports; (2) whether `/api/show` returns the architecture keys for the chosen models
(`sizing` prints "cannot size" otherwise; pick another model rather than editing the script); (3) whether the small model gets the
injection email right: **whatever it answers is the take**, a failure is a lesson, not a retake; (4) whether Foundry Local installs
and a model for the NVIDIA GPU downloads (skip scene `probe-screen`'s Foundry line if not).

## Prerequisites and setup (off camera)
1. `nvidia-smi` in a terminal: note GPU name, total and free memory. Close other GPU-hungry apps (browser video, games) so the free-memory number is honest, then reopen the numbers.
2. `ollama list`; pull the models decided above (`ollama pull <name>`). Start the Ollama app/service; confirm `http://127.0.0.1:11434` answers (the CLI's `probe` does that).
3. LM Studio: load one small model, Developer tab, toggle **Start server** (or `lms server start`); the base URL is `http://localhost:1234/v1`.
4. Optional Foundry Local: `foundry model list --device gpu`, pick a small chat alias, `foundry chat <alias>` once to download it; keep a terminal with the model running and `foundry server status` ready (the port is dynamic: copy it).
5. `cd series/copilot-ai/episodes/23-local-llms-on-your-own-gpu/src`; `python -m pytest -q ..` (33 passed) as a sanity check.
6. Do one full dry run of every command in the table below and keep the outputs as the safety takes. Run `ollama stop <model>` for each model before the final take so the warm-up load time shown by `bench` is a real cold load.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `sizing-screen` | `screens/sizing.jpg` | Terminal: `nvidia-smi` (GPU name, memory) then `python -m local_llm sizing <small-model> <big-model> --context 4096 32768`. Visible: each FITS / DOES NOT FIT line and "largest context that fits". Then `ollama run <big-model>` or any request to it, and `ollama ps` showing the real CPU/GPU split, to compare estimate and reality. Real output only |
| `bench-screen` | `screens/bench.jpg` | Terminal: `python -m local_llm bench <small-model> <big-model> --repeats 3`: the markdown table with placement, context, load seconds (warm-up), prompt and generation tokens per second. Real numbers, unedited. If the big model is 100% GPU as well, say so and pick a larger one before publishing |
| `extract-screen` | `screens/extract.jpg` | Terminal: `python -m local_llm extract <small-model> --email samples/invoice-email.txt --schema samples/invoice.schema.json --expected samples/invoice-expected.json`. Visible: the JSON, the "nothing left this machine" line, and the match/differ lines. Show the email file briefly beside it (the injection line and the bank-change line). Keep whatever the model really answers |
| `probe-screen` | `screens/probe.jpg` | Terminal: `python -m local_llm probe --extra foundry=http://127.0.0.1:<port>/v1` with Ollama, LM Studio and (if installed) Foundry Local running: one line per server with its model ids. Then, in the same recording, `python -m local_llm --host http://example.com models` to show the non-local refusal (it fails before any network call) |

Masking: nothing tenant-related appears. Hide the Windows user name in prompts/paths (use a short prompt such as `PS mg-lab>`), and
do not show any browser tabs.

## Tear-down
1. `ollama stop <model>` (or let keep-alive expire) and quit LM Studio's server toggle; `foundry service stop`/close the Foundry terminal if it was started (the Foundry docs name `foundry server status` and `foundry server restart`; confirm the stop command on the day with `foundry --help`).
2. Remove models pulled only for the recording if disk space matters: `ollama rm <name>`; LM Studio and Foundry Local models via their own UIs/CLIs.
3. Delete the saved terminal outputs if they contain local paths; nothing in this episode creates cloud resources.
