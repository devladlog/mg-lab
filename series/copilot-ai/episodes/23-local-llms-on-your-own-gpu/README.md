# DEVLADLOG Copilot & AI #23 - Local LLMs on Your Own GPU

Contoso's accounts-payable team gets vendor emails with invoice numbers, amounts and bank details. Legal asks: *can an AI read
those without the text leaving the building?* This episode answers with a model on your own GPU and a small toolkit that
makes the answer measurable (Python standard library only, no SDK to install):

- **sizing**: will this model fit in the GPU's memory? Weights (the real file size from the server) plus the KV cache (computed
  from the model's own architecture numbers) against free VRAM, and the largest context that still fits.
- **bench**: tokens per second from the timings the server reports, warm-up excluded, and where the model really sits (GPU or CPU)
  computed from `GET /api/ps`.
- **extract**: schema-constrained extraction (the JSON schema goes in Ollama's `format` field) on a Contoso invoice email that also
  contains a prompt-injection line and a bank-detail change request, with a local-only guard that refuses non-local endpoints.
- **probe**: which local OpenAI-compatible servers answer: Ollama, LM Studio, Microsoft Foundry Local.

Series plan: [`../../README.md`](../../README.md) ("Licensing reality": local models run on the recording laptop). Shared lab:
[`../../../LAB.md`](../../../LAB.md). Previous: [episode 22, OpenAI and Gemini APIs side by side](../22-openai-and-google-gemini-apis-side-by-side/)
(not built yet when this was written) and [episode 20, the same questions through several cloud models in Foundry](../20-azure-ai-foundry-agent-service-with-multiple-model/).
Next: [episode 24, One Task, Five AIs](../24-one-task-five-ais-evaluating-copilot-claude-gpt-ge/), which adds a local model to the
cloud ones. Category episodes: [Generative AI and LLMs](../../../ai/episodes/15-generative-ai-llms/),
[Azure OpenAI enterprise patterns](../../../ai/episodes/02-azure-openai-enterprise-patterns/),
[AI governance and compliance](../../../ai/episodes/07-ai-governance-compliance/).

| Path | What it is |
|---|---|
| [`src/local_llm/ollama.py`](src/local_llm/ollama.py) | Ollama native client: `/api/tags`, `/api/ps`, `/api/show`, `/api/chat` (format, options, keep_alive, think), unload; timings to tokens/s; `placement()` |
| [`src/local_llm/openai_compat.py`](src/local_llm/openai_compat.py) | Client for any OpenAI-compatible local server (`/v1/models`, `/v1/chat/completions`) and `probe()` |
| [`src/local_llm/sizing.py`](src/local_llm/sizing.py) | KV-cache formula, fit estimate, largest context, `nvidia-smi` reader |
| [`src/local_llm/bench.py`](src/local_llm/bench.py), [`extract.py`](src/local_llm/extract.py), [`cli.py`](src/local_llm/cli.py) | Benchmark, structured extraction with a small schema validator, CLI `probe | models | sizing | bench | extract` |
| [`src/samples/`](src/samples) | `invoice-email.txt` (fictional, with an injection line), `invoice.schema.json`, `invoice-expected.json`, `bench-prompt.txt` |
| [`tests/`](tests) | 33 pytest tests against a scripted HTTP stand-in (tests only) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 750 words) and the recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/23-local-llms-on-your-own-gpu
python3 -m pip install -r src/requirements.txt     # pytest only
python3 -m pytest -q                                # 33 passed
cd src
python3 -m local_llm --help
```

Live, on the recording laptop (needs Ollama running and a model pulled; nothing here calls a cloud service):

```bash
python -m local_llm probe                           # Ollama :11434, LM Studio :1234
python -m local_llm models                          # disk (tags) and memory (ps)
python -m local_llm sizing --context 4096 32768     # reads free VRAM from nvidia-smi, or --vram-gib 24
python -m local_llm bench <model> --repeats 3
python -m local_llm extract <model> --email samples/invoice-email.txt --schema samples/invoice.schema.json --expected samples/invoice-expected.json
```

Verified here (Linux container, Python 3.13): `python -m pytest -q` gives 33 passed; the CLI starts. **Not verified without the
laptop:** any real call to Ollama, LM Studio or Foundry Local, any real tokens-per-second figure, the VRAM numbers of the real GPU,
and whether a given model keeps the injection email's category right. No model was run in this build (no GPU, 8 GB shared RAM).

## What we learned / gotchas

- **Default context is 4096 tokens** (Ollama FAQ). A long email silently being cut is the first local-model surprise; set
  `options.num_ctx` (the tools take `--num-ctx`) and check `context_length` in `GET /api/ps`. A bigger context costs KV-cache
  memory: that is what `sizing` computes.
- **"Fits" means 100% GPU.** `ollama ps` prints where a model is loaded; the FAQ says "100% GPU" means loaded entirely on the GPU.
  `GET /api/ps` has `size` and `size_vram` so a tool can compute the split, as `placement()` does. A model that spills into system
  RAM still runs, only much slower: always read the placement next to the tokens per second.
- **The sizing is an estimate.** Weights = the file size from `/api/tags`; KV cache = 2 x layers x KV heads x head dimension x
  context x 2 bytes (f16), with `head_dim = embedding_length / head_count`. The Ollama FAQ gives the cache types `f16` (default),
  `q8_0` ("about half the memory") and `q4_0` ("about a quarter"), valid when Flash Attention is on, applied to all models. Models
  with a different head dimension, sliding-window layers or compute buffers will differ; the 1 GiB margin is our own number, not
  from any documentation. Trust `ps` over `sizing`.
- **Model keep-alive:** models stay loaded for 5 minutes by default; `keep_alive: 0` unloads, and per the API docs an empty
  `messages` array with `keep_alive: 0` unloads without generating (what `unload()` sends). The first request after that includes
  load time, which is why `bench` has a warm-up run that is excluded from the medians.
- **Tokens per second:** the native API returns durations in nanoseconds (`eval_count`, `eval_duration`, `prompt_eval_*`,
  `load_duration`). The docs describe the fields but do not give a formula; generation speed = `eval_count / eval_duration` after
  the unit conversion is our own arithmetic. The OpenAI-compatible endpoint has token usage but no per-phase timings, so the
  compat client can only report wall-clock speed, which includes prompt processing.
- **Structured output:** `format` accepts `"json"` or a JSON schema object. The model is constrained to the schema, but the
  *values* can still be wrong or follow the email's injected instruction; the extraction test checks the schema and the expected
  fields separately. Our validator is a deliberate subset (type, required, enum, minimum, items, additionalProperties false).
- **Ollama binds 127.0.0.1:11434 by default**; exposing it needs `OLLAMA_HOST` (FAQ), and the FAQ says nothing about authentication
  for the local API. The CLI therefore refuses non-local hosts unless `--allow-remote`; that guard checks the URL, it is not a
  firewall.
- **OpenAI compatibility is partial.** Ollama's page lists `/v1/chat/completions`, `/v1/responses` (stateless), `/v1/completions`,
  `/v1/embeddings` and `/v1/models`; `tool_choice`, `logit_bias`, `n` and logprobs are not supported on chat completions. The API
  key is required by OpenAI clients but ignored. LM Studio's page lists `/v1/models`, `/v1/responses`, `/v1/chat/completions`,
  `/v1/embeddings`, `/v1/completions` on `http://localhost:1234/v1` (its examples assume port 1234).
- **Microsoft's own local runtime is Foundry Local** (Microsoft Foundry on Windows; also macOS Apple silicon and Linux per its
  overview). It is built to ship inside applications: a curated catalogue, automatic GPU/NPU/CPU selection, an SDK, and an
  *optional* OpenAI-compatible REST server and CLI. Learn says plainly it is optimised for one user at a time and is not a server
  inference stack (use vLLM or similar for many users). The CLI is **preview**; install with `winget install Microsoft.FoundryLocal`;
  the REST server gets a **dynamic port** on every start, read it with `foundry server status` and append `/v1`.
- **Which GPU?** NVIDIA lists the GeForce RTX 5090 *Laptop* GPU with 24 GB GDDR7 (the desktop card is a different product). The
  recording laptop is a laptop: let `nvidia-smi` say what the lab machine has, and quote that number.
- **Open-weight models have licences.** Read each model's licence before using it for work; nothing in this episode checks them.
- Models named in the demo are examples: the Ollama library changes constantly. Pick from what `ollama list` shows on the day.

## References

Microsoft Learn
- [What is Foundry Local?](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local)
- [Foundry Local CLI reference (preview)](https://learn.microsoft.com/azure/foundry-local/reference/reference-cli) and [Use the Foundry Local CLI](https://learn.microsoft.com/azure/foundry-local/how-to/how-to-use-foundry-local-cli)
- [Integrate Foundry Local with inference SDKs (local REST server)](https://learn.microsoft.com/azure/foundry-local/how-to/how-to-integrate-with-inference-sdks)
- [Get started with Foundry Local on Windows](https://learn.microsoft.com/windows/ai/foundry-local/get-started)

Vendors (official documentation, read 21 Nov 2026)
- Ollama: [API: chat](https://docs.ollama.com/api/chat), [ps](https://docs.ollama.com/api/ps), [tags](https://docs.ollama.com/api/tags), [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), [FAQ](https://docs.ollama.com/faq); unload and `/api/show` model_info keys: [docs/api.md in the ollama repository](https://github.com/ollama/ollama/blob/main/docs/api.md)
- LM Studio: [OpenAI compatibility endpoints](https://lmstudio.ai/docs/developer/openai-compat), [Local server](https://lmstudio.ai/docs/developer/core/server)
- NVIDIA: [GeForce RTX 50 Series laptops](https://www.nvidia.com/en-us/geforce/laptops/50-series/) (memory per laptop GPU)

No devladlog.com blog guide: this series is built from vendor documentation only.
