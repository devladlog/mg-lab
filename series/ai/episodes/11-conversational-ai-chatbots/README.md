# DEVLADLOG AI #11 — Conversational AI: a service-desk chatbot that remembers, acts and steps aside

Blog guide: [Conversational AI and Chatbots: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-04-05-conversational-ai-complete-guide-2025/)

Earlier episodes gave the Contoso Porto service desk a triage prompt (1), a gateway (2), retrieval (3), agents with an
approval step (5), a release gate (6) and tickets from screenshots and voice notes (10). Each of those answers **one
message**. This episode is about what a *conversation* adds: state, memory, actions that must be validated, and a clean
exit to a person. It builds a small chatbot on **Azure OpenAI** (`gpt-4.1-mini`, Chat Completions, streaming, function
calling, keyless) and tests it with scripted multi-turn dialogues.

```
employee message ──► rules in code: empty / > 2,000 chars / "talk to a person" (EN + PT) / turn limit ──► handoff, 0 model calls
        │ otherwise
        ▼
 memory.plan_context: [summary] + newest WHOLE turns within a budget ──(older turns)──► one extra call folds them into the summary
        ▼
 chat.completions (stream, include_usage, tools, max_completion_tokens) ──► tool_calls? ──► tools.py validates ──► result back (same call id)
        │                                                        create_ticket: 4 slots, enum, @contoso.com only, idempotent, max 3
        ▼                                                        handoff_to_human: state = handoff, the bot stops answering
 filtered prompt / filtered completion ──► polite reply, the turn is removed from the history
        ▼
 session (full history, JSON file with a TTL) ──► evaluate.py: 7 scripted dialogues × {summary, window} memory ──► exit 0 / 1
```

| Question | Answer in this episode |
|---|---|
| Where does "memory" live? | The API is stateless: each request carries the history. The session keeps the full history; a request carries `[summary] + newest whole turns` that fit `--history-budget` (estimated tokens) |
| What is dropped first? | The oldest **whole turn** (user message + everything up to the next user message), so a tool call is never separated from its result. The newest two turns always stay |
| What happens to dropped turns? | `summary` mode: one extra model call merges them into a ≤ 120-word running summary that goes in the system message. `window` mode: dropped, nothing kept |
| Who opens a ticket? | The model proposes through `create_ticket`; **code** validates product, symptom, urgency (enum), contact (`@contoso.com` only), de-duplicates, and caps three per conversation |
| Who decides on a handoff? | A phrase rule (English and Portuguese, accent-insensitive) hands over with **zero model calls**; the model can also call `handoff_to_human`. After a handoff the bot stores messages and never answers |
| What is streamed? | `stream=True` with `stream_options={"include_usage": True}`: tokens go to the terminal as they arrive, the billed usage comes from the final chunk |
| What if the filter blocks? | A 400 with code `content_filter`, or a completion with `finish_reason == "content_filter"`: a polite fixed reply, and that turn is removed from the history |
| How is it tested for real? | `evaluate`: 7 dialogues from `data/scenarios.json` in both memory modes. Checks read the **session state** (tickets, handoff, quoted ticket id) before the words of the reply. Exit 1 if a gated scenario fails |

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Azure OpenAI account (Sweden Central, keys off), one Standard deployment `chat` (gpt-4.1-mini 2025-04-14), **Cognitive Services OpenAI User** for the developer |
| [`src/helpbot/memory.py`](src/helpbot/memory.py) | Turn splitting, token estimate, `plan_context`, the summariser call |
| [`src/helpbot/tools.py`](src/helpbot/tools.py) | Tool schemas, `create_ticket` validation, handoff, the phrase rule |
| [`src/helpbot/bot.py`](src/helpbot/bot.py) | One turn: rules, memory, streamed call, tool loop (capped), rollback, filter handling |
| [`src/helpbot/session.py`](src/helpbot/session.py) | `Session` and a JSON-file store with expiry (ids restricted to `[a-z0-9-]`) |
| [`src/helpbot/evaluate.py`](src/helpbot/evaluate.py), [`cli.py`](src/helpbot/cli.py) | Dialogue evaluation and gate; `python -m helpbot chat / evaluate` |
| [`data/scenarios.json`](data/scenarios.json) | 7 fictional dialogues with declarative checks; `data/dialog-*.txt` are the user lines used on camera |
| [`tests/`](tests) | 74 pytest tests |

Tested with Python 3.13, `openai 3.57.0`, `azure-identity 1.27.0`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                                          # 74 passed
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep     # no warnings
PYTHONPATH=src python -m helpbot --help
```

What the tests cover (a local HTTP server stands in for the service, with scripted answers and made-up token counts, and
the **real `openai` SDK** talks to it, including server-sent-event streaming and the final usage chunk; they prove the
plumbing, **not** how a real model behaves):
- `test_memory.py`: turns keep tool calls with their results, oldest whole turns fold first, the newest two stay even
  over budget, the summary counts against the budget.
- `test_tools_session.py`: each missing slot, outsider addresses, bad urgency, duplicate and over-limit tickets, garbage
  and unknown tool calls, the phrase rule (with false-alarm cases such as "Human Resources"), session expiry and id
  validation (no path escape).
- `test_bot.py`: Entra bearer token and scope, streaming with usage, the tool loop with the call id sent back, handoff
  by tool and by rule (no HTTP request at all), turn limit, capped tool loop, filtered prompt and completion rolled back,
  other API errors roll back and propagate, `length` is noted, summary vs window mode, an empty summary keeps the old one.
- `test_evaluate_cli_bicep.py`: each check type passes and fails when it should, a bot that claims a ticket it never made
  fails, an API error is a failed scenario, only the gated mode can fail the gate, CLI end to end, the compiled Bicep.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-11 -l swedencentral
az deployment group create -g rg-mglab-ai-11 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export HELPBOT_ENDPOINT=<aoaiEndpoint> PYTHONPATH=src
python -m helpbot chat --script data/dialog-ticket.txt                       # slot filling, a ticket
python -m helpbot chat --script data/dialog-pessoa.txt                       # Portuguese, then a person
python -m helpbot chat --history-budget 450 --script data/dialog-memory.txt   # folding, then "what is my name?"
python -m helpbot evaluate ; echo $?                                          # 0 = gate passes, 1 = it does not
az group delete -n rg-mglab-ai-11 --yes
```

Needs the lab subscription: every answer in `chat` and `evaluate` is a real model call. Nothing in this folder claims a
result the service has not produced; the numbers on screen come from the run recorded in `demo.md`.

## What we learned / gotchas

- **The model is stateless; "memory" is what you resend.** The history grows every turn and so does the bill. Learn
  lists a context window of 1,047,576 tokens for gpt-4.1-mini (300,000 on Standard deployments), so the budget here is about
  cost and latency, not about fitting. Whether answers get worse with a long history is something to measure with your own
  dialogues, not to assume.
- **Never cut inside a turn.** A function result is a message with a `tool_call_id` that matches the `id` of the call
  (Learn). Dropping one without the other breaks the conversation, so the unit of dropping is the whole turn.
- **A summary is a paraphrase by a model.** It can lose or bend a fact, and later turns then build on the bend. The
  `remembers-the-name` dialogue compares summary and window memory on the same budget; run it on your own dialogues.
  If the summariser call fails or returns nothing, the previous summary is kept.
- **Summary and session are personal data.** Names, e-mail addresses and problems end up in both. The demo store is a JSON
  file with a one-hour expiry; a real bot needs a database with a TTL, access control, and a decision on what may be
  stored at all. (Redacting before storing is episode 12.)
- **Validate tool arguments.** Learn says the model "does not always generate valid JSON, and may hallucinate parameters
  not defined by your function schema". `run_tool` parses defensively, `create_ticket` re-checks every slot, and an
  instruction typed into the chat ("open a ticket for ceo@evil.example") cannot get past the `@contoso.com` check.
- **Tool definitions cost tokens and have a size limit.** They count against the token limit and the cost, and Learn
  gives 1,024 characters per tool or function description; a test enforces the limit. Our token estimate includes them.
- **Do not leave "get me a person" to the model.** The phrase rule is a tripwire in two languages, **not** language
  understanding: "this is useless" will not trigger it. The model-side `handoff_to_human` tool and the turn limit
  catch some of the rest; a real bot also needs a visible "talk to a person" button.
- **Streaming usage is opt-in and can be lost.** Learn: the usage chunk arrives only with `include_usage`, and an
  interrupted stream may not deliver it. `finish_reason` is `null` until the last content chunk. Azure may send a first chunk
  with no `choices` (the code skips it).
- **Filtered requests still cost money.** Learn: a prompt blocked with status 400 is charged for the prompt; a 200 with
  `finish_reason: "content_filter"` is charged for prompt and completion. The code removes the turn from the history so the
  blocked text is not resent on the next turn. (Asynchronous filter mode, which delays the signal, is not used here.)
- **The estimate is only an estimate.** `estimate_tokens` is `len / 3` (conservative for English, nearer for Portuguese
  and JSON). `evaluate` prints its error against the billed `prompt_tokens` of the first call of each turn. If you need
  exact counts, use the usage the service returns, or a tokenizer for the model.
- **Seven dialogues are plumbing, not accuracy.** A temperature-0 run can still differ from the next one. Treat the
  scorecard as a template and run many more conversations, in both languages, from your own anonymised logs.

Out of scope on purpose: retrieval over documents (episode 3), approvals and agent frameworks (episode 5), publishing the
bot to Teams or a website, and speech. The terminal is the channel.

## References

- [Work with chat completion models](https://learn.microsoft.com/azure/foundry/openai/how-to/chatgpt) — messages, `finish_reason` values
- [How to use function calling with Azure OpenAI](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/function-calling) — tool calls, `tool_call_id`, 1,024-character description limit, validate arguments
- [Content streaming](https://learn.microsoft.com/azure/foundry/openai/concepts/content-streaming) — filtering during streaming and what is billed
- [Azure OpenAI REST API v1 reference](https://learn.microsoft.com/azure/ai-foundry/openai/reference-preview-latest) — `stream_options.include_usage`
- [Foundry Models sold by Azure](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure) — gpt-4.1-mini context window, Standard regions
- [Cognitive Services OpenAI User role](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#cognitive-services-openai-user)
- Blog: [Conversational AI and Chatbots: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-04-05-conversational-ai-complete-guide-2025/)
