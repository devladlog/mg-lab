# DEVLADLOG AI #3 — RAG patterns and vector search: hybrid retrieval you can measure

The `hr-bot` team from episode 2 now needs its bot to answer from the (fictional) **Contoso HR handbook** — and to
prove it. This episode builds retrieval-augmented generation on **Azure AI Search** the way you'd want to ship it:
chunked by document structure, indexed as text *and* vectors, retrieved four different ways so the options can be
**compared on labelled questions**, and answered with **numbered citations that code checks**.

```
data/handbook/*.md ──chunk by section──► embeddings (text-embedding-3-small) ──push──► Azure AI Search index "hr-handbook"
                                                                                       · BM25 text fields
question ──► keyword | vector | hybrid (RRF) | hybrid + semantic ranker ◄─────────────── · HNSW vector field + vectorizer
         ──► top 5 chunks, numbered [1]..[5] ──► chat model ──► answer + check_citations()
```

- **Keyless end to end.** The search service has API keys disabled; your user gets the three search roles; the
  index's **vectorizer** embeds questions inside the service using the search service's **system-assigned managed
  identity** (Cognitive Services OpenAI User on the Azure OpenAI account). Azure OpenAI has key auth disabled too.
- **Chunking by structure**: one chunk per Markdown section, long sections split on sentence boundaries with
  overlap (Learn's starting point: ~512 tokens ≈ 2,000 characters, 25% overlap), and every chunk prefixed with
  `Document > Section` so it stands on its own.
- **Four retrieval modes from one function**: `keyword` (BM25), `vector` (text vector query → vectorizer),
  `hybrid` (both, fused with Reciprocal Rank Fusion), `hybrid_semantic` (hybrid + semantic ranker).
- **A retrieval scorecard** (`hit@1`, `hit@5`, MRR per mode) over 16 labelled questions + 2 out-of-scope ones.
- **Grounded answers**: the model only sees numbered sources inside delimiters, must cite `[n]` or reply with one
  fixed "not found" sentence; `check_citations()` rejects invented, missing or truncated citations.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | AI Search **Basic** (system identity, `disableLocalAuth`, semantic ranker free plan), Azure OpenAI (custom subdomain, keys off, `embed-small` = text-embedding-3-small v1 and `chat` = gpt-5-mini 2025-08-07, pinned), role assignments |
| [`src/hrrag/chunking.py`](src/hrrag/chunking.py) | Heading-aware Markdown chunker with overlap; HTML comments (boilerplate) never indexed |
| [`src/hrrag/index_schema.py`](src/hrrag/index_schema.py) | `SearchIndex`: key + filterable fields, searchable text, 1536-d HNSW vector field, Azure OpenAI vectorizer (keyless), semantic configuration |
| [`src/hrrag/embeddings.py`](src/hrrag/embeddings.py) | OpenAI SDK on the Azure OpenAI v1 endpoint with an Entra token provider; batched embeddings with size checks |
| [`src/hrrag/ingest.py`](src/hrrag/ingest.py) | CLI: create/update index, chunk, embed, `merge_or_upload` in batches (≤ 1,000 docs), fail on any rejected document |
| [`src/hrrag/retrieve.py`](src/hrrag/retrieve.py) | `query_kwargs()` for the four modes, `AzureRetriever` (DefaultAzureCredential) |
| [`src/hrrag/fusion.py`](src/hrrag/fusion.py) | Reference RRF (`1/(rank+60)`), used by the local double and in tests |
| [`src/hrrag/local.py`](src/hrrag/local.py) | Offline test double: BM25 + hashed (non-semantic!) vectors + RRF |
| [`src/hrrag/answer.py`](src/hrrag/answer.py) | Prompt with numbered, delimited sources; `check_citations()`; CLI that prints answer + sources |
| [`src/hrrag/evaluate.py`](src/hrrag/evaluate.py) | CLI: scorecard per mode, out-of-scope report (`--local` or against Azure) |
| [`data/handbook/`](data/handbook) | 6 fictional Contoso HR policy documents (25 sections) |
| [`data/questions.jsonl`](data/questions.jsonl) | 18 labelled questions: exact-term ("form HR-31"), paraphrases ("vacation" vs "annual leave"), 2 out of scope |
| [`tests/`](tests) | 38 pytest tests (see below) |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                       # 38 passed (test_bicep.py is skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep      # no warnings
PYTHONPATH=src python -m hrrag.ingest --search-endpoint x --aoai-endpoint y --dry-run   # 25 chunks from 6 documents
PYTHONPATH=src python -m hrrag.evaluate --local # plumbing check with the offline double (not a benchmark)
```

What the tests cover:
- `test_search_sdk.py` runs the **real `azure-search-documents` SDK** against a local HTTP stub and asserts the
  exact REST calls: `PUT /indexes('hr-handbook')?api-version=2026-10-01` with the vectorizer and semantic config,
  `docs/search.index` with `mergeOrUpload` and vectors, a 207 partial failure that must raise, and the hybrid +
  semantic query body (`vectorQueries[kind=text, k=50]`, `queryType=semantic`). Each mode sends only what it needs.
- `test_embeddings_and_answer.py` runs the **real `openai` SDK** against a stub of the v1 endpoint: Entra bearer
  token, batching (16 per request), wrong embedding size fails loudly, no `temperature` for gpt-5-mini, valid /
  invalid / missing / truncated citations, the "not found" answer, no model call when nothing was retrieved, and
  retrieved text that tries to close the `<</SOURCES>>` block.
- `test_index_schema.py` checks the serialized index: 1536 dimensions, profile → HNSW (cosine) + vectorizer,
  vectorizer with no key and no identity (= system managed identity), semantic config, single key field.
- `test_bicep.py` compiles the Bicep and checks: search keyless with a system identity and the free semantic plan,
  Azure OpenAI keyless with pinned deployments, the search identity's OpenAI User assignment, the three dev roles.
- `test_chunking.py` / `test_fusion_and_local.py`: chunk ids are valid document keys, overlap rules, every
  labelled section exists in the handbook, RRF math, keyword search nails exact codes, and retrieval always
  returns *something* even for out-of-scope questions.

Tested with Python 3.13, `azure-search-documents 12.1.0` (targets REST `2026-10-01`), `openai 3.57.0`,
`azure-identity 1.27.0`, Bicep CLI as installed in the build container.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-rag -l swedencentral
az deployment group create -g rg-mglab-rag -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export SEARCH=https://<search>.search.windows.net AOAI=https://<aoai>.openai.azure.com
PYTHONPATH=src python -m hrrag.ingest   --search-endpoint $SEARCH --aoai-endpoint $AOAI
PYTHONPATH=src python -m hrrag.evaluate --search-endpoint $SEARCH
PYTHONPATH=src python -m hrrag.answer "If I don't use all my vacation this year, can I keep some days?" \
   --search-endpoint $SEARCH --aoai-endpoint $AOAI
```

## What we learned / gotchas

- **Search never says "no".** Ranking orders what exists; an out-of-scope question ("company car policy") still
  returns five chunks. Refusal has to be designed into the answer step (fixed sentence + a test), and citations
  have to be checked in code — the model's word that it used the sources isn't evidence.
- **Same embedding model at index and query time.** The vectorizer embeds questions; our ingest embeds chunks. Learn
  is explicit: use the same model for both, and changing the vectorizer doesn't re-embed existing documents. The
  index pins `modelName` and the vector field's `dimensions` (1536 for text-embedding-3-small); `embed_texts()`
  fails if a vector has the wrong size.
- **The Free search tier doesn't fit this design.** Learn: the Free tier doesn't support managed identities, which
  the keyless vectorizer needs, and the "try for free" page says it doesn't support semantic ranking (while the
  region table lists some regions that do). We use **Basic**, which supports both, and delete it after recording.
- **Semantic ranker billing is opt-in.** With `semanticSearch: free` there's a monthly free allowance; after it's
  used, semantic requests fail with a billing error instead of charging. Charges only apply to `queryType=semantic`
  with a non-empty search string.
- **Indexing results are per document.** A batch can return HTTP 207 with some documents rejected; `upload()` checks
  every result and raises with the keys. Batches are capped at 1,000 documents / 16 MB.
- **RRF's `k` (60) is not the vector query's `k`** (nearest neighbours, 50 here). Learn calls this out; mixing them
  up is a common tuning mistake.
- **The SDK refuses bearer tokens over plain HTTP**, so the stub tests use a fake `AzureKeyCredential`; production
  code paths use `DefaultAzureCredential` only.
- **The local double is not semantic.** Its hashed vectors only catch spelling-level similarity. `--local` numbers
  check the harness, they are not a benchmark; the screen recording uses the real index.

## References

- [Relevance scoring in hybrid search using RRF](https://learn.microsoft.com/azure/search/hybrid-search-ranking) — `1/(rank+k)`, k = 60; semantic ranking runs after RRF; score ranges
- [Configure a vectorizer in a search index](https://learn.microsoft.com/azure/search/vector-search-how-to-configure-vectorizer) — same model at index and query time; changing it doesn't re-embed
- [Azure OpenAI vectorizer](https://learn.microsoft.com/azure/search/vector-search-vectorizer-azure-open-ai) — parameters, system-assigned identity when `apiKey`/`authIdentity` are omitted, dimensions per model
- [Chunk large documents for RAG and vector search](https://learn.microsoft.com/azure/search/vector-search-how-to-chunk-documents) — 512 tokens / 25% overlap starting point; text-embedding-3-small max input 8,191 tokens
- [Semantic ranking overview](https://learn.microsoft.com/azure/search/semantic-search-overview) and [Enable or disable semantic ranker billing](https://learn.microsoft.com/azure/search/semantic-how-to-enable-disable)
- [Try Azure AI Search for free](https://learn.microsoft.com/azure/search/search-try-for-free) and [feature availability by tier](https://learn.microsoft.com/azure/search/search-sku-tier#feature-availability-by-tier)
- [Connect using roles](https://learn.microsoft.com/azure/search/search-security-rbac) (role names and IDs) and [Enable or disable RBAC](https://learn.microsoft.com/azure/search/search-security-enable-roles)
- [Index large data sets (batching)](https://learn.microsoft.com/azure/search/search-how-to-large-index) and [Service limits](https://learn.microsoft.com/azure/search/search-limits-quotas-capacity) — 1,000 documents / 16 MB per indexing request
- [Hybrid query how-to](https://learn.microsoft.com/azure/search/hybrid-search-how-to-query) and [Vector quickstart (Python)](https://learn.microsoft.com/azure/search/search-get-started-vector?pivots=python)
- [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule) — text-embedding-3-small v1 GA, retirement 2028-02-09; gpt-5-mini 2025-08-07 retirement 2027-07-13 (checked 21 Nov 2026)
- Blog: [RAG Patterns — Complete Guide](https://www.devladlog.com/articles/ai/2026-03-31-rag-patterns-complete-guide-2026/)
