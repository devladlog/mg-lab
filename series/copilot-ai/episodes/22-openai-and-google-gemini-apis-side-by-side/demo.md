# Demo shot list - Copilot & AI #22 OpenAI and Google Gemini APIs Side by Side

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant / accounts | **No Microsoft tenant, no Azure subscription.** Two vendor accounts owned by the channel owner: an OpenAI API account with billing on, and a Google AI Studio project with a **paid-tier** Gemini API key. The lab Administrator types both keys off camera into the terminal session (`$env:OPENAI_API_KEY`, `$env:GEMINI_API_KEY`); they are never written to a file, never committed and never shown |
| Licences | OpenAI and Gemini API access are pay-as-you-go, no seat licence. Not verified: whether the owner's projects have access to `gpt-6.2-sol` and `gemini-3.8-flash` (check the model list on the recording day; pass `--openai-model` / `--gemini-model` otherwise) |
| Estimated cost | List prices in `src/samples/prices.json` (checked 2026-11-21): GPT-6.2 Sol US$2 input / US$10 output per 1M tokens; Gemini 3.8 Flash US$0.75 / US$3.75 per 1M tokens until 31 December 2026, then US$1.50 / US$7.50. The three tasks make about 8 short requests per vendor, well under US$0.50 in total, even with retakes (an estimate, not measured: the run prints its own estimate) |
| Data | Fictional Contoso data only. **Use the paid-tier Gemini key**: the free tier's content is used to improve Google products (pricing page). The `data-screen` scene shows that row on the public pricing page |
| Recording machine | Windows lab laptop, PowerShell 7 (dark theme, 18 pt), Python 3.10+; `python -m pip install -r src/requirements.txt` (Azure Identity is only needed for the optional Azure path and can be skipped) |

## What was verified where

| Step | Build container (Linux) | Needs the owner's keys |
|---|---|---|
| Request bodies, strict-schema conversion, validators, tool loops, error mapping, cost arithmetic | yes: 42 pytest tests, the real SDKs against a scripted HTTP endpoint | live call |
| `schema` and `payloads` commands | yes, no network | none: record them anywhere |
| `run extract / tool / truncate` | no | **record real output**, whatever it is |
| Gemini `steps`, `function_call`, `function_result` and status `incomplete` shapes | built from SDK types and docs, **not captured live** | confirm on the first live `run tool` and `run truncate`; if the live service rejects the stateless tool input, fix `gemini_adapter.run_tool` and the test, and change `tool-code` and its narration |
| OpenAI stateless tool loop with `include: reasoning.encrypted_content` | same | same |
| Azure OpenAI through `--openai-base-url` | no | optional: needs an Azure OpenAI resource, not part of the script |

Open points that can change the script: (1) the model names (`gpt-6.2-sol`, `gemini-3.8-flash`) and the prices in `usage-code` against the two pricing pages on the recording day; (2) whether the 16-token run truncates on both vendors (the `truncate-screen` narration describes an empty answer on reasoning models: if a vendor returns visible text, say so); (3) whether the model's extract answer validates: if it prints a PROBLEM line, keep it, that is the point of the scene.

## Setup
1. `cd` into the episode folder, `python -m pip install -r src/requirements.txt`, `python -m pytest -q` (42 passed).
2. `cd src`, then set the two keys off camera.
3. Off camera, run `run extract`, `run tool`, `run truncate` once each as the safety take. Check the tool run: the output must list `get_vendor_renewals` and a total for Litware Security and Fabrikam Cloud (30,900 euros).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `schema-screen` | `screens/schema-conversion.jpg` | Terminal: `python -m llm_sidebyside schema`, then `payloads extract`. No key, no network |
| `extract-screen` | `screens/extract-run.jpg` | Terminal: `python -m llm_sidebyside run extract --vendor both`: both result lines (model, status, tokens, cost) and the JSON. Real output |
| `truncate-screen` | `screens/truncate-run.jpg` | Terminal: `python -m llm_sidebyside run truncate --vendor both`: status and token counts per vendor. Real output |
| `data-screen` | `screens/gemini-pricing-free-vs-paid.jpg` | Browser, ai.google.dev Gemini API pricing, Gemini 3.8 Flash, Standard: free vs paid columns and the "Used to improve our products" row. Public page, no sign-in |

No screen needs a Microsoft licence or a mock.

## Tear-down
1. Close the terminal so the key variables disappear; confirm nothing was written to a file or shell history (`Get-Content (Get-PSReadLineOption).HistorySavePath | Select-String KEY`).
2. Revoke or rotate the two API keys if they appeared anywhere recorded; delete unused takes.
3. Nothing to delete in Azure or Microsoft 365: nothing was created there.
