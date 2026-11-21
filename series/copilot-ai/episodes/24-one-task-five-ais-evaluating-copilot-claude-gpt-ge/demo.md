# Demo shot list - Copilot & AI #24 One Task, Five AIs

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Microsoft side | Momento Galático lab tenant: **`alex.demo`** (E5 trial licence, **no** Microsoft 365 Copilot add-on) signs in to **Microsoft Copilot Chat** in the browser (`copilot.cloud.microsoft`, per Learn the primary URL). Free Copilot Chat must be available to the tenant (episode 2 shows how; if it is blocked by tenant settings, fix that first, do not fake it). **NEEDS LICENCE (not in the lab):** the Microsoft 365 Copilot add-on is only needed for the optional Chat API insert, not for this episode; price per `series/LAB-REQUESTS.md` (read 21 Nov 2026 on Microsoft's pricing page): 30.00 USD per user per month, paid yearly, marketing price, real price at checkout; the owner decides, the script does not depend on it |
| Other AIs | The **owner's own API keys** for OpenAI, Anthropic and Google (Gemini API), typed off camera into environment variables, never in a file or on screen. Cost: 7 tasks x 1 repeat = 7 short requests per vendor (a few thousand tokens in total); the price depends on the model chosen and is **not verified here**: read each vendor's price page, write the three figures here `__________`, and prefer a small/cheap model if it is enough. Set a low spending limit in each vendor console if the console offers one |
| Local model | Ollama on the recording laptop with the model from episode 23 (OpenAI-compatible endpoint `http://127.0.0.1:11434/v1`) |
| Recording machine | The lab Windows laptop (host): browser for Copilot Chat and the Learn page, Windows Terminal (dark, 18 pt) in the repo folder, VS Code for the review sheet, Python 3.10+ |
| Code execution | The `business-days` task runs model-written Python. Either accept the restricted runner on the laptop (README: not a security boundary; it only runs code that passes the allow-list) or record without `--allow-code-exec` and show the "skipped" rows. Decide before recording and tell the viewer which |

## What was verified where

| Step | Build container (Linux) | Needs keys / lab |
|---|---|---|
| Adapters (request and response shapes), scoring, sandbox, blind review, runner, CLI | yes: 56 pytest tests, canned vendor-shaped responses and a local stand-in HTTP server (tests only) | - |
| Every real vendor call, real scores, latency, tokens, prices | no | **first real run** |
| Copilot Chat answers | no | **collected by hand in the lab tenant** |

Open points that change the script: (1) whether each vendor accepts the model ids and the request (a 400 on first run is
information: read the error row, fix the config, never edit the script around it); (2) whether Copilot Chat answers the injection
email correctly: **whatever it says is the take**; (3) if every AI scores 1.00 on a task the task was too easy: add a harder
one before publishing; (4) if the account used for Copilot Chat has web search on, say so on camera (tasks are self-contained).

## Prerequisites and setup (off camera)
1. `cd series/copilot-ai/episodes/24-one-task-five-ais-evaluating-copilot-claude-gpt-ge/src`; `python -m pytest -q ..` (56 passed).
2. Copy `samples/config.json` to a **private working copy outside the repo** (it will contain model ids only; keys come from the environment). Replace the four `REPLACE-...` model names with real ids from each vendor's models page and the local name from `ollama list`; copy the real per-million prices from each vendor's price page into `prices`. Remove nothing else.
3. Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` in the terminal session (off camera). `python -m five_ais plan --config <copy> --tasks samples/tasks.json` must show OK for claude, gpt, gemini and local (copilot says the answers file is missing until step 4).
4. `python -m five_ais prompts --config <copy> --tasks samples/tasks.json --write-template copilot-answers.json` prints the exact text of each task. In Copilot Chat as `alex.demo`, open a **new chat for each task**, paste the printed text, copy Copilot's answer **unedited** into `copilot-answers.json` (JSON-escape quotes and line breaks, or paste through a JSON-aware editor). Note the date and time.
5. Safety take: `python -m five_ais run --config <copy> --tasks samples/tasks.json --out safety.json --allow-code-exec` (or without the flag). Keep it.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `licence-screen` | `screens/chat-api-licence.jpg` | Browser on the Learn page "Overview of the Microsoft 365 Copilot Chat API (preview)": the title with "(preview)" and the **Licensing** section (add-on licence required; no support without it). Scroll so both are visible. This is Microsoft's own page |
| `copilot-screen` | `screens/copilot-chat.jpg` | Browser, Microsoft Copilot Chat signed in as `alex.demo` (mask the tenant name and any email in the account menu): the `policy-unanswerable` or `invoice-json` prompt pasted, and Copilot's real answer. Real answer, no regeneration unless the first attempt errored |
| `run-screen` | `screens/run.jpg` | Terminal: `python -m five_ais run --config <copy> --tasks samples/tasks.json --out results.json --allow-code-exec`: the progress lines per provider and task, then the scorecard table, the per-category table, and the Errors / Failed checks lists. Real output only; if a provider errored, show it as it is |
| `blind-screen` | `screens/blind-review.jpg` | VS Code split: `review-sheet.md` open at one task with answers A to E and **no provider names**, beside the terminal after `python -m five_ais unblind ...` showing the report with the human column filled. Score the sheet for real before the take (1 to 5), without opening `review-key.json` first |

Masking: the three API keys are never on screen (check the terminal history and the shell prompt); the lab tenant name and the Copilot account
email are masked; no vendor console pages are shown.

## Tear-down
1. Delete `copilot-answers.json`, `results.json`, `safety.json`, `review-key.json`, `scores.json` and the private config copy (they contain model ids and Copilot's answers; do not commit them).
2. Clear the three environment variables (close the terminal). Revoke or delete any API key created only for the recording, and remove any spending limit changes you no longer need.
3. Delete the Copilot Chat conversations created for the recording from Copilot Chat's history (the app's own delete option), and `ollama stop <model>`.
