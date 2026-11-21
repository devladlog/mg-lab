# DEVLADLOG AI #1 — Prompt engineering for LLMs, measured

We treat a prompt like code: versioned, reviewed and **evaluated against a labelled dataset** before it ships.
The scenario is ticket triage for a fictional Contoso IT helpdesk: read a ticket, return category, priority, a
one-line summary, whether a human must look at it, and whether the ticket tries to inject instructions.

Two prompt versions run against the same 20 fictional tickets (three of them are prompt-injection attempts):

| Prompt | What it does |
|---|---|
| `v1` | The prompt most teams start with: one instruction, ticket pasted in, "answer as JSON" |
| `v2` | System message with role, definitions, rules and explicit fallback · three few-shot examples as user/assistant pairs · spotlighting (delimiters + data marking) for the untrusted ticket text · structured outputs with a strict JSON Schema |

The harness prints a scorecard per prompt: schema-valid answers, category and priority accuracy, injection attempts
resisted, and tokens in/out (few-shot examples and the schema cost input tokens — the scorecard makes that visible).

| Path | What it is |
|---|---|
| [`src/triage/schema.py`](src/triage/schema.py) | Output contract (`TRIAGE_SCHEMA`) and `strict_schema_problems()`, a checker for the structured-outputs JSON Schema subset documented on Learn |
| [`src/triage/spotlight.py`](src/triage/spotlight.py) | Spotlighting: neutralise delimiter look-alikes, data-mark whitespace with `^`, wrap in `<<TICKET>>` delimiters |
| [`src/triage/prompts.py`](src/triage/prompts.py) | Prompt versions `v1` and `v2` (system message, few-shot examples) |
| [`src/triage/request.py`](src/triage/request.py) | Builds the Chat Completions body; drops `temperature`/`max_tokens` for reasoning models (GPT-5 family, o-series) |
| [`src/triage/evaluate.py`](src/triage/evaluate.py) | Scoring, scorecard, Entra ID client for the Azure OpenAI v1 endpoint, CLI (`--dry-run`, `--show`) |
| [`data/tickets.jsonl`](data/tickets.jsonl) | 20 labelled fictional tickets (17 normal, 3 injection attempts) |
| [`tests/`](tests) | 37 pytest tests, including the real OpenAI SDK against a local stub of the v1 endpoint |

## Run the tests (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q          # 37 passed
PYTHONPATH=src python -m triage.evaluate --data data/tickets.jsonl --prompt v1 --prompt v2 --dry-run
```

`test_sdk_roundtrip.py` starts a local HTTP server that imitates `https://<resource>.openai.azure.com/openai/v1/`
and runs the real `openai` client against it: it checks the path, the `Bearer` token from the Entra token provider,
that `response_format` is strict JSON Schema, that `temperature` is not sent to a reasoning model, that a 429 with
`retry-after-ms` is retried, and that a refusal is handled. Tested locally with `openai 3.57.0`, `jsonschema 4.26.0`,
Python 3.13.

## Run it for real (needs an Azure OpenAI deployment)

```bash
az login                                            # identity with "Cognitive Services OpenAI User" on the resource (lab: labadmin, rg-mglab-ai-01)
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
PYTHONPATH=src python -m triage.evaluate --data data/tickets.jsonl \
    --prompt v1 --prompt v2 --deployment triage-mini --model gpt-5-mini --show
```

No API keys: the client uses `DefaultAzureCredential` with `get_bearer_token_provider(..., "https://ai.azure.com/.default")`
and the v1 endpoint, exactly as in the Learn samples. `--model` is the model behind the deployment; it decides which
parameters are allowed. The deployment name goes in the request's `model` field.

## What we learned / gotchas

- **`temperature: 0` is not a universal habit any more.** Reasoning models (GPT-5 family, o-series) don't support
  `temperature`, `top_p`, the penalties, `logprobs` or `max_tokens`; with Chat Completions they need
  `max_completion_tokens`. `request.py` builds the body per model family instead of hard-coding it.
- **Reasoning tokens count toward `max_completion_tokens`.** Set it too low and you get `finish_reason: "length"`
  with no usable answer; the scorer reports that as an error instead of silently scoring garbage.
- **Strict schemas are a subset of JSON Schema.** `maxLength`, `pattern`, `format`, `minimum`… are rejected, every
  property must be `required` and every object needs `additionalProperties: false`. `strict_schema_problems()` catches
  this in a unit test instead of at runtime — which is why the 20-word limit on `summary` lives in the instructions,
  not in a `maxLength`.
- **Free-form "answer in JSON" is not a contract.** Nothing stops a v1-style prompt from returning a markdown code
  fence, extra prose or its own label casing. The scorer tolerates a fence but counts anything off-schema as invalid.
  (Record the live v1 result in the demo; don't predict it in the script.)
- **Spotlighting reduces indirect prompt injection; it doesn't remove it.** Delimiters alone can be subverted, so we
  strip delimiter look-alikes and the marker character first (ticket `A02` tries exactly that). Layer it with Prompt
  Shields on the deployment and never give the model's output authority it doesn't need.
- **Order of few-shot examples matters.** Learn notes recency bias; keep examples varied, cover edge cases (we cover a
  P1 outage, a security incident and a vague ticket) and re-run the evaluation when you change them.

## References

- [Prompt engineering techniques](https://learn.microsoft.com/azure/foundry/openai/concepts/prompt-engineering)
- [System message design](https://learn.microsoft.com/azure/foundry/openai/concepts/advanced-prompt-engineering)
- [Safety system messages — spotlighting](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/system-message)
- [Structured outputs (supported models, JSON Schema limitations)](https://learn.microsoft.com/azure/foundry/openai/how-to/structured-outputs)
- [Azure OpenAI reasoning models (unsupported parameters, reasoning effort)](https://learn.microsoft.com/azure/foundry/openai/how-to/reasoning)
- [Prompt Shields and spotlighting](https://learn.microsoft.com/azure/foundry/openai/concepts/content-filter-prompt-shields)
- [Microsoft Entra ID authentication for Azure OpenAI](https://learn.microsoft.com/azure/foundry-classic/openai/how-to/managed-identity)
- [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule) — gpt-5-mini 2025-08-07 is GA, retirement 2027-07-13 (checked 21 Nov 2026)
- Blog: [Prompt Engineering — Complete Guide](https://www.devladlog.com/articles/ai/2025-02-03-prompt-engineering-complete-guide-2025/)
