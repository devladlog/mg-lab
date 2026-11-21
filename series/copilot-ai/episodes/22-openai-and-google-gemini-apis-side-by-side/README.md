# Copilot & AI #22: OpenAI and Google Gemini APIs Side by Side

The same three Contoso tasks, run against the OpenAI **Responses API** and the Google **Gemini Interactions API**, through one neutral contract and two small adapters. The episode compares the *shape* of the APIs (schemas, tools, limits, usage, errors, data handling), not model quality. For Claude on Azure see [episode 21](../21-claude-in-the-microsoft-ecosystem/), for several models behind Foundry Agent Service see [episode 20](../20-azure-ai-foundry-agent-service-with-multiple-model/).

The Contoso scenario is the same as episode 21: Fabrikam Cloud, Northwind Print, Adventure Works Telecom and Litware Security, 45,000 euros per year in total.

## What we build

| Path | Purpose |
|---|---|
| `src/llm_sidebyside/contract.py` | The tasks written once: system prompt, vendor text, canonical JSON schema, tool spec, the client-side tool, and `check_extract` (validation the APIs do not do) |
| `src/llm_sidebyside/dialects.py` | Pure functions: canonical task to OpenAI request body and Gemini request body; strict-schema converter with a change report |
| `src/llm_sidebyside/openai_adapter.py` | Responses API: extract, truncate, stateless tool loop; refusal and `incomplete` handling |
| `src/llm_sidebyside/gemini_adapter.py` | Interactions API: the same three tasks; function-result steps |
| `src/llm_sidebyside/models.py` | One `Outcome` / `Usage` shape and the cost estimate (reasoning tokens counted per vendor) |
| `src/llm_sidebyside/errors.py` | Both SDKs' exceptions mapped to `quota, rate_limit, auth, bad_request, not_found, server, network`; retry with `Retry-After` |
| `src/llm_sidebyside/cli.py` | `payloads`, `schema` (no network) and `run` (real APIs) |
| `src/samples/vendors.json`, `prices.json` | Fictional vendor data (one note contains an injected instruction, as in episode 21); dated price list |
| `tests/` | 42 tests: the real `openai` and `google-genai` SDKs against a scripted HTTP endpoint |
| `script.yaml`, `demo.md` | Video script and shot list |

## Run it

```bash
python -m pip install -r src/requirements.txt          # per user is fine: pip install --user
python -m pytest -q                                      # 42 passed, no network, no keys
cd src
python -m llm_sidebyside schema                          # what strict mode changes, what Gemini ignores
python -m llm_sidebyside payloads extract                # the two request bodies, exactly as sent
export OPENAI_API_KEY=...  GEMINI_API_KEY=...            # your own keys, typed in your shell, never in a file
python -m llm_sidebyside run extract --vendor both       # real calls, costs a few cents
python -m llm_sidebyside run tool
python -m llm_sidebyside run truncate
```

Default models: `gpt-6.2-sol` and `gemini-3.8-flash` (override with `--openai-model`, `--gemini-model` or `OPENAI_MODEL`, `GEMINI_MODEL`). Exit codes: 0 ok, 1 a task failed or the answer did not validate, 2 configuration (missing key).

Azure OpenAI: the same adapter works against an Azure OpenAI v1 endpoint with `--openai-base-url https://<resource>.openai.azure.com/openai/v1/` and the key of that resource (**not tested**; `--openai-model` is then your deployment name).

## Verification

Verified in the build container (Linux, Python 3.13, `openai` 3.57.0, `google-genai` 3.6.1): all 42 tests pass. The tests do not mock the SDKs; they replace the HTTP transport, so request bodies, auth headers, response parsing, usage fields and error classes are the real SDK behaviour. **Not verified:** any live call. The response shapes in the tests (for example Gemini `steps`, `function_call`, `function_result`, status `incomplete`) are built from the SDK types and the docs, not captured from the live services; `demo.md` lists what the first live run must confirm.

## Differences the code encodes

| | OpenAI Responses | Gemini Interactions |
|---|---|---|
| Endpoint | `POST /v1/responses` | `POST /v1/interactions` |
| Instructions | developer message first in `input` | `system_instruction` |
| Structured output | `text.format` `json_schema`, `strict: true`; every property required, `additionalProperties: false`, optional = nullable | `response_format` with `mime_type` and `schema`; optional stays optional |
| Keywords not enforced | strict subset (others are rejected or dropped by our converter) | `minLength`, `maxLength`, `minProperties`, `maxProperties`, `uniqueItems`, `contains`, `minContains`, `maxContains` accepted but ignored |
| Token limit | `max_output_tokens` (minimum 16, includes reasoning tokens) | `generation_config.max_output_tokens` |
| Cut-off signal | `status: incomplete` | `status: incomplete` |
| Thinking tokens in usage | inside `output_tokens` (`reasoning_tokens` is a detail) | separate `total_thought_tokens` |
| Stored by default | application state 30 days; `store: false` | 1 day free tier, 55 days paid tier; `store: false` |
| Tool result | `function_call_output` item by `call_id` | `function_result` step by `call_id` |

## Gotchas

- Strict mode changes your schema: our converter reports every change instead of hiding it (`python -m llm_sidebyside schema`).
- Neither API enforces the arithmetic or `minLength` / `uniqueItems`; `check_extract` does.
- `max_output_tokens` on a reasoning model can be spent entirely on thinking: an empty answer with status `incomplete` is normal.
- A 429 from OpenAI can mean billing quota (`insufficient_quota`), which retrying cannot fix.
- Gemini's free tier data is used to improve Google products, the paid tier's is not (pricing page). Do not send Contoso data through a free key.
- Gemini 3.8 Flash's listed price doubles on 1 January 2027 (`prices.json` carries both).
- Prices and model names change: `prices.json` is dated 2026-11-21 and sourced.
- The Interactions API is a newer surface; the SDK 3.x exposes it as `client.interactions`. Check the docs before you pin a version.

## References

- OpenAI: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Function calling](https://developers.openai.com/api/docs/guides/function-calling), [Responses create](https://developers.openai.com/api/docs/api-reference/responses/create), [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)
- Google: [Interactions API](https://ai.google.dev/gemini-api/docs/interactions), [Structured output](https://ai.google.dev/gemini-api/docs/structured-output), [Function calling](https://ai.google.dev/gemini-api/docs/function-calling), [Pricing](https://ai.google.dev/gemini-api/docs/pricing)
