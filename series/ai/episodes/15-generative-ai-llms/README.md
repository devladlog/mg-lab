# DEVLADLOG AI #15 — Generative AI and LLMs: what the model does with your prompt

Blog guide: [Generative AI: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-07-10-generative-ai-complete-guide-2025/)

Episodes 1 to 14 used a language model as a component: prompts (1), a gateway (2), retrieval (3), agents (5), a release
gate (6), monitoring (8), fine-tuning (9), screenshots (10), a chatbot (11). This episode opens the box on the model
itself, using the Contoso HR bot's leave questions (the same fictional handbook as episode 3): **why the same prompt gives
different wording, how sure the model is, what text costs, what the user waits for, and what has to fit in the window.**
Five small tools, one Python package, a **non-reasoning** model (`gpt-4.1-mini`) on Azure OpenAI, keyless.

| Question | Tool | What it measures |
|---|---|---|
| What does text cost, in two languages? | `llmprobe tokens` (offline) | The same six policy sentences in English and Portuguese, counted with `cl100k_base` and `o200k_base` |
| How sure is the model? | `llmprobe probe` | `logprobs` + `top_logprobs`: probability of the winning letter, the runner-up, entropy of the candidates; each question asked without and with the handbook; an answer/escalate gate at a threshold |
| What do temperature and seed change? | `llmprobe sample` | The same prompt N times per setting (t=0 / t=1, with and without `seed`): distinct answers, mean similarity, **whether the required facts survive**, `system_fingerprint`s. Exit 1 if a fact is lost or an answer is cut off |
| What is the user waiting for? | `llmprobe stream` | Time to first *content* chunk, streaming vs blocking total time, chunks vs billed completion tokens |
| What fits in the window? | `llmprobe budget` | Window plan (output reserve, system, question), rank-order chunk packer, the estimate compared with the **billed** `usage.prompt_tokens` |

Real output of the offline tool (run here, tiktoken 0.14.0; the six sentences are in `data/pairs.json`):

```
sentence      cl100k_base en/pt   pt/en      o200k_base en/pt   pt/en
leave               16/27          1.69           16/20          1.25
request             24/31          1.29           24/25          1.04
carry               15/19          1.27           15/16          1.07
lost                21/30          1.43           21/27          1.29
sick                16/21          1.31           16/18          1.12
parental            21/29          1.38           21/25          1.19
total              113/157         1.39          113/131         1.16
```

That is six sentences, not a study: Portuguese needed about 39 % more tokens than English with `cl100k_base` and about 16 %
more with `o200k_base` on this sample. Measure your own text.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | Azure OpenAI account (Sweden Central, keys off), one Standard deployment `chat` = gpt-4.1-mini 2025-04-14 (NoAutoUpgrade); **Cognitive Services OpenAI User** for the developer |
| [`src/llmprobe/tokens.py`](src/llmprobe/tokens.py) | tiktoken counting, token pieces, EN/PT comparison |
| [`src/llmprobe/probe.py`](src/llmprobe/probe.py) | Next-token distribution from `logprobs`, variant merging (`C`, ` C`, `C)`), entropy, answer/escalate gate |
| [`src/llmprobe/sampling.py`](src/llmprobe/sampling.py) | Setting grid, similarity, required-facts check, `system_fingerprint`, gate |
| [`src/llmprobe/stream.py`](src/llmprobe/stream.py) | Streaming with `include_usage`, skips empty-`choices` chunks, injectable clock |
| [`src/llmprobe/budget.py`](src/llmprobe/budget.py) | Limits from Learn (1,047,576 window, 300,000 on Standard, 32,768 output), plan, packer, request check |
| [`src/llmprobe/guards.py`](src/llmprobe/guards.py) | Refuses reasoning-family model names for experiments that need temperature / logprobs |
| [`src/llmprobe/client.py`](src/llmprobe/client.py), [`cli.py`](src/llmprobe/cli.py) | Entra ID client for the v1 endpoint; `python -m llmprobe tokens / probe / sample / stream / budget` |
| [`data/`](data) | Fictional handbook section (`handbook_leave.md`), 4 multiple-choice cases, the sampling spec, 6 EN/PT sentence pairs |
| [`tests/`](tests) | 57 pytest tests |

Tested with Python 3.13, `openai 3.57.0`, `tiktoken 0.14.0`, `azure-identity 1.27.0`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                                   # 57 passed
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep      # no warnings
PYTHONPATH=src python -m llmprobe tokens                    # offline, real tiktoken
PYTHONPATH=src python -m llmprobe budget --dry-run --context-budget 120   # plan only
```

What the tests cover (the "model" is a lookup table behind a local HTTP server; the real `openai` SDK talks to it; all
numbers are made up, so they prove parsing, arithmetic, gates and request shapes, **not model behaviour**):
- `test_tokens_guards.py`: our tiktoken use reproduces Learn's own example ("Tell me about the solar system." is the seven
  tokens 41551 757 922 279 13238 1887 13 in `cl100k_base`); model-to-encoding mapping; the sample sentences; reasoning-family
  names refused.
- `test_probe.py`: probabilities from `top_logprobs`, token variants merged, entropy 0 when sure and 1 bit for a coin flip, missing
  `logprobs` is an error, request shape (`logprobs`, `top_logprobs`, `temperature: 0`, `max_completion_tokens`, no `max_tokens`),
  the 0 to 20 limit, the gate.
- `test_sampling.py`: `seed` is sent only when set, distinct/similarity/fact-rate/fingerprint arithmetic, `\b5\b` does not match
  inside `15`, the failure reasons.
- `test_stream_budget.py`: the stream skips the filter-annotation chunk and the usage chunk, first-content time is not first-chunk
  time, chunks are not tokens, `length` is reported, plan arithmetic and limits, the packer stops at the first chunk that does not fit.
- `test_cli_and_bicep.py`: each command end to end with exit codes (0 / 1 / 2), nothing is called for a reasoning model, the compiled
  Bicep (keyless, one Standard deployment, version pinned, only the OpenAI User role).

The tiktoken vocabulary files are downloaded on first use (a few MB, cached); with no network and no cache the tests skip.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-15 -l swedencentral
az deployment group create -g rg-mglab-ai-15 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export LLMPROBE_ENDPOINT=<aoaiEndpoint> PYTHONPATH=src
python -m llmprobe probe
python -m llmprobe sample --runs 8 ; echo exit=$?       # 1 if a required fact was lost
python -m llmprobe stream --runs 3
python -m llmprobe budget --context-budget 120          # too small: the Carry-over section is dropped
python -m llmprobe budget --context-budget 400
az group delete -n rg-mglab-ai-15 --yes
```

Nothing in this folder claims a result the service hasn't produced; the numbers on screen come from the run in `demo.md`.

## What we learned / gotchas

- **Same prompt, different wording is normal.** With default settings Learn says the same question is likely to get a
  different response. `sample` therefore checks that the *facts* (a regular expression each: `\b5\b`, `31 March`) are present
  in every answer, not that the text repeats. Do not write tests that compare generated text for equality.
- **`seed` is best effort.** Learn (reproducible output, preview): determinism is not guaranteed, watch `system_fingerprint`, match all
  other parameters, and larger token limits generally give less deterministic results even with a seed. The table prints the
  fingerprints seen so a backend change is visible.
- **Temperature and logprobs are for non-reasoning models.** Learn lists `temperature`, `top_p`, the penalties, `logprobs`,
  `top_logprobs`, `logit_bias` and `max_tokens` as unsupported for reasoning models. `guards.py` refuses `o*` and `gpt-5*` names
  (override with `--allow-unverified-model` if you have checked a specific model).
- **`top_logprobs` is 0 to 20** (Learn REST reference); `logprobs` must be `true` to use it. Token variants of one answer (`C`, ` C`,
  `C)`) are separate entries, so the tool merges them before reporting a probability.
- **A token probability is not the probability the answer is true.** The gate in `probe.decide` is a routing rule; pick its threshold
  on labelled questions, never from the table alone. Questions the model has no evidence for can still produce a confident letter.
- **Streaming chunks are not tokens, and not every chunk has `choices`.** The v1 reference says that with `include_usage` the final chunk has an
  empty `choices` array and `usage`; the content-streaming article shows the first chunk with prompt filter results and `choices: []`.
  By default content is buffered for the content filter and arrives in buffer-sized chunks (Learn). If the stream is interrupted
  you may not get the usage chunk (Learn). Learn also notes that in its tests the last 15 to 30 words of a streamed response could be
  returned before the guardrail was applied; use non-streaming calls where that is unacceptable.
- **The window is a shared budget.** Learn: input, output and reasoning tokens share the context budget, and max output tokens is an upper limit, not a
  reservation. `gpt-4.1-mini` is listed with a 1,047,576-token window, **300,000 on Standard deployments** and 32,768 maximum output.
  `budget.py` refuses a plan above these numbers and a request whose prompt plus `max_completion_tokens` does not fit.
- **Estimates are not invoices.** `tiktoken` maps `gpt-4.1-mini` to `o200k_base` (tiktoken's mapping, not a Learn statement) and counts message text only;
  the service bills the chat format as well. `budget` prints the real difference to `usage.prompt_tokens` instead of hard-coding an overhead.
- **Packing in rank order.** `fit_chunks` stops at the first chunk that does not fit. Skipping it to squeeze a lower-ranked chunk in would
  silently change what the model treats as the best evidence. The demo drops the Carry-over section on purpose to show the answer without evidence.
- **Portuguese costs more tokens.** On this six-sentence sample, see the table; the newer encoding narrows the gap. It affects cost, latency and how much retrieved
  text fits, so size budgets per language.

## References

- [Reproducible output (seed, system_fingerprint)](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/reproducible-output)
- [Azure OpenAI REST API reference: chat completions (`logprobs`, `top_logprobs` 0 to 20, `seed`, `temperature`, `stream_options`)](https://learn.microsoft.com/azure/foundry/openai/reference)
- [REST API v1 preview reference (`include_usage`, final chunk with empty `choices`, `system_fingerprint`)](https://learn.microsoft.com/azure/ai-foundry/openai/reference-preview-latest)
- [Azure OpenAI reasoning models (unsupported parameters)](https://learn.microsoft.com/azure/foundry/openai/how-to/reasoning)
- [Content streaming (default buffering, annotation chunks, last-segment note)](https://learn.microsoft.com/azure/foundry/openai/concepts/content-streaming)
- [Foundry Models sold by Azure: gpt-4.1 series capabilities (context window, 300,000 on Standard, 32,768 max output; "Understand model token limits")](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
- [Region availability for Foundry Models sold by Azure](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability) — gpt-4.1-mini 2025-04-14 Standard listed for swedencentral (checked 21 Nov 2026)
- [Token counting in AI (the "Tell me about the solar system." example)](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/ai-system-app-token-counting)
- [Understand tokens](https://learn.microsoft.com/dotnet/ai/conceptual/understanding-tokens)
- [Role-based access control for Azure OpenAI (Cognitive Services OpenAI User)](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/role-based-access-control)
- Blog: [Generative AI: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-07-10-generative-ai-complete-guide-2025/)
