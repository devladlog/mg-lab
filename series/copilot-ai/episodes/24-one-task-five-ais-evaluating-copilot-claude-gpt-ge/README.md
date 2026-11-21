# DEVLADLOG Copilot & AI #24 - One Task, Five AIs: Evaluating Copilot, Claude, GPT, Gemini and a Local Model

Contoso's procurement team asks: *which AI should we use for what?* Opinions are cheap, so this episode builds a small,
honest evaluation harness (Python standard library only) and runs the **same seven tasks, with the same words, through five AIs**:

| Contestant | How it is called | Why |
|---|---|---|
| Microsoft Copilot Chat | **By hand**, answers pasted into a file | Learn: the Microsoft 365 Copilot Chat API is **preview** (Graph `/beta`) and "available at no extra cost to users with a Microsoft 365 Copilot add-on license"; support without the add-on "isn't currently available". The lab has no add-on seat, so the free Copilot Chat is used through its web UI and nothing is faked |
| Claude | Anthropic Messages API | `POST /v1/messages` |
| GPT | OpenAI Responses API | `POST /v1/responses` |
| Gemini | Gemini `generateContent` | `POST /v1beta/models/{model}:generateContent` |
| A local model | OpenAI-compatible `/v1/chat/completions` of Ollama, LM Studio or Foundry Local | the model from [episode 23](../23-local-llms-on-your-own-gpu/) |

The seven tasks (`src/samples/tasks.json`, all Contoso, fictional) are scored by **plain rules, not by another model**: a grounded
policy question with arithmetic, a question the policy does *not* answer (the right answer is "NOT STATED"), JSON extraction from an
email that carries a prompt-injection line, a Python function that is **executed against five test cases**, a Microsoft Graph
PowerShell cmdlet name (a hallucination probe), a word-limited summary, and a discount-then-VAT calculation. A **blind review**
step (shuffled labels A to E, human score 1 to 5, then unblind) adds what rules cannot see.

Series plan: [`../../README.md`](../../README.md) ("Licensing reality"). Shared lab: [`../../../LAB.md`](../../../LAB.md). Related in
the series: [episode 20, the same idea inside Foundry with several cloud models](../20-azure-ai-foundry-agent-service-with-multiple-model/),
[episode 21, Claude](../21-claude-in-the-microsoft-ecosystem/), [episode 22, OpenAI and Gemini side by side](../22-openai-and-google-gemini-apis-side-by-side/),
[episode 23, local models](../23-local-llms-on-your-own-gpu/), [episode 2, Copilot Chat in a real tenant](../02-microsoft-365-copilot-chat-in-a-real-tenant/).
Category episodes: [Prompt engineering for LLMs](../../../ai/episodes/01-prompt-engineering-for-llms/),
[AI model monitoring and drift](../../../ai/episodes/08-ai-model-monitoring-drift/).

| Path | What it is |
|---|---|
| [`src/five_ais/providers.py`](src/five_ais/providers.py) | One adapter per wire format (OpenAI, Anthropic, Gemini, local OpenAI-compatible) plus the manual provider; errors become result rows |
| [`src/five_ais/scoring.py`](src/five_ais/scoring.py), [`sandbox.py`](src/five_ais/sandbox.py) | Rule checks; restricted runner for model-written Python (opt-in, see below) |
| [`src/five_ais/runner.py`](src/five_ais/runner.py), [`blind.py`](src/five_ais/blind.py), [`cli.py`](src/five_ais/cli.py) | Run, summarise, report, blind review; CLI `plan | prompts | run | blind | unblind | report` |
| [`src/samples/`](src/samples) | `tasks.json` (7 tasks), `config.json` (placeholder models and zero prices) |
| [`tests/`](tests) | 56 pytest tests: request/response shapes per vendor, scoring (a passing and a failing answer for every task), sandbox, runner, blind review, CLI end to end |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 780 words) and the recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/24-one-task-five-ais-evaluating-copilot-claude-gpt-ge
python3 -m pip install -r src/requirements.txt      # pytest only
python3 -m pytest -q                                 # 56 passed
cd src
python3 -m five_ais plan    --config samples/config.json --tasks samples/tasks.json
python3 -m five_ais prompts --config samples/config.json --tasks samples/tasks.json --write-template copilot-answers.json
```

Live (the owner's own API keys, typed off camera, never committed; models are named in a private copy of `config.json`):

```bash
export OPENAI_API_KEY=...  ANTHROPIC_API_KEY=...  GEMINI_API_KEY=...     # PowerShell: $env:OPENAI_API_KEY = "..."
python -m five_ais run --config config.json --tasks samples/tasks.json --out results.json --allow-code-exec
python -m five_ais blind results.json                # review-sheet.md (read it) and review-key.json (do not open yet)
python -m five_ais unblind results.json --key review-key.json --scores scores.json
```

Verified here (Linux container, Python 3.13): `python -m pytest -q` gives 56 passed; `plan` and `prompts` run. **Not verified without
keys and the lab:** every real API call (the adapters are written from each vendor's reference pages and tested against canned
responses of that shape), any real score, price or latency, and Copilot Chat's real answers. No cloud service was contacted.

## What we learned / gotchas

- **Naming.** Learn's requirements page says Microsoft 365 Copilot is now named **Microsoft Copilot** and Microsoft 365 Copilot Chat
  **Microsoft Copilot Chat**, with the app at `copilot.cloud.microsoft`. Copilot Chat needs an Entra account and an eligible
  Microsoft 365 subscription but "Microsoft Copilot license: Not required for eligible users".
- **Copilot has an API, but not for the lab.** The Chat API (Graph `POST /beta/copilot/conversations` then `.../{id}/chat`) is preview,
  needs delegated permissions (`Sites.Read.All`, `Mail.Read`, `People.Read.All`, `OnlineMeetingTranscript.Read.All`, `Chat.Read`,
  `ChannelMessage.Read.All`, `ExternalItem.Read.All`, all of them), uses enterprise **and web** grounding by default, and returns
  text only. That makes it a different thing from a model API: it answers from your tenant. Learn also lists a *Work IQ* Chat API
  (`workiq.svc.cloud.microsoft`, permission `WorkIQAgent.Ask`); its page does not state its licensing or how it relates to the Graph
  one, so it is not evaluated here.
- **Copilot Chat is not a controlled experiment.** You cannot set its model, temperature or system prompt, and Microsoft decides what
  runs behind it; record the date and the exact prompt. For fairness the harness defaults to `instructions_mode: "inline"`: the
  instructions are prepended to the question for **every** AI, so all five see identical text. `"system"` mode puts them in each
  API's system field instead (better practice for apps, but then Copilot sees something different). Use one chat per task for
  Copilot so earlier answers do not leak into later ones.
- **Temperature is going away.** Anthropic's API version `2026-10-21` (latest on its versions page; `2023-06-01` and `2023-01-01` are
  listed too) *removes* `temperature`, `top_p` and `top_k`: a request that sends any of them returns 400 on every model. Gemini's
  docs say "Gemini 4 and Gemini 3.6+ models ignore custom values for `temperature`, `top_p`, and `top_k`". So the harness sends no
  sampling parameters, the Anthropic adapter refuses (before any request) a configured temperature on a version that removed it, and
  reproducibility comes from **repeats**, not seeds.
- **Do not assume where the text is.** OpenAI's guide says `output_text` is an SDK convenience and "It is not safe to assume that the
  model's text output is present at `output[0].content[0].text`"; reasoning models add other items. The adapter joins the
  `output_text` parts of every `message` item. `store` defaults to true, so the harness sends `store: false`. A status other than
  `completed` is an error row, not a short answer.
- **Gemini has two APIs now.** The docs call `generateContent` "legacy" in the page title and say "For new projects ... we strongly
  recommend using the new Interactions API" (`POST /v1beta/interactions`), while another page says `generateContent` "remains fully
  supported". This harness uses `generateContent` because its request/response reference was readable; the Interactions API is not
  implemented (its system-instruction and generation-config fields could not be confirmed). Thinking tokens are reported separately
  (`thoughtsTokenCount`); the adapter adds them to the output count and skips parts flagged `thought`. Whether and how vendors bill
  those tokens: check each price page.
- **Anthropic auth headers.** The API overview lists `Authorization: Bearer <token>` as required "unless `x-api-key` is set" and calls
  `x-api-key` a "legacy fallback ... still supported"; the version page's curl uses `x-api-key`, which is what the adapter sends.
  `anthropic-version` is required on every request (default `2026-10-21`, configurable).
- **Errors are results.** A 401, a timeout or an empty answer scores 0 and is listed under "Errors"; nothing is retried silently and
  the API key never appears in an error row (tested). A task with no checks would score 0 for everyone (tested).
- **Running model-written code is dangerous.** `--allow-code-exec` is off by default (the python checks then show as "skipped", never
  as passed). When on: an AST allow-list refuses imports outside a short list and calls such as `open`, `eval`, `exec`, `getattr`;
  the code runs in a separate `python -I` process with an empty environment, a temp directory and a timeout (plus CPU/memory limits
  on POSIX only). **This is not a security boundary.** For anything beyond the demo run the harness in a throwaway VM.
- **Seven tasks are a smoke test.** Differences of one task are noise. Add tasks from your own work, run `repeats` of 3 or more for
  the API models, and read the failed checks, not just the average. If every AI scores 1.00 the tasks were too easy.
- **Prices and models are never hard-coded.** `config.json` has `REPLACE-...` model names and zero prices on purpose; the harness
  refuses to run a provider with an unset model or missing key (`plan` shows why). Copy real model ids and prices from each vendor's
  pages on the day. Copilot Chat has no per-token price in this table: it is free for eligible users in this lab.
- **Number matching is deliberately forgiving about separators** (`19,803`, `19 803,00`, `19.803,00` all count as 19803); it tries
  both readings, so a wrong number that happens to equal the other reading would pass. The tasks avoid such collisions.

## References

Microsoft Learn
- [Overview of the Microsoft 365 Copilot Chat API (preview)](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/ai-services/chat/overview)
- [Create copilotConversation](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/ai-services/chat/copilotroot-post-conversations) and [copilotConversation: chat](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/ai-services/chat/copilotconversation-chat)
- [Work IQ - copilotConversation: chat](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/rest/copilotconversation-chat)
- [Microsoft Copilot requirements](https://learn.microsoft.com/copilot/plan/microsoft-copilot-requirements) (rename note, licence table) and [Microsoft Copilot overview](https://learn.microsoft.com/copilot/plan/copilot-overview)

Vendors (official documentation, read 21 Nov 2026)
- Anthropic: [Messages API](https://platform.claude.com/docs/en/api/messages), [API overview (headers)](https://platform.claude.com/docs/en/api/overview), [API versions](https://platform.claude.com/docs/en/api/versioning)
- OpenAI: [Create a response](https://developers.openai.com/api/reference/resources/responses/methods/create), [Text generation guide](https://developers.openai.com/api/docs/guides/text)
- Google: [generateContent reference](https://ai.google.dev/api/generate-content), [Generate Content API (legacy) getting started](https://ai.google.dev/gemini-api/docs/generate-content/get-started) and [text generation](https://ai.google.dev/gemini-api/docs/generate-content/text-generation), [Migrating to the Interactions API](https://ai.google.dev/gemini-api/docs/migrate-to-interactions)
- Ollama: [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)

No devladlog.com blog guide: this series is built from vendor documentation only.
