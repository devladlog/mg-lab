# DEVLADLOG Deep Dive #2 — An enterprise AI copilot on SharePoint that respects permissions (Azure OpenAI + Power Platform + SharePoint)

An HR policy copilot in Copilot Studio. An employee and a manager ask the same question about salary bands: the
manager gets the answer with a citation, the employee gets *"I couldn't find this in the documents you have access
to."* Not because the model was told to keep a secret: the employee's request never retrieves that document.

```
SharePoint libraries ──(Graph, Sites.Selected)──► indexer/ ──(chunks + vectors + group_ids)──► Azure AI Search (keys off)
  Policies → Employees group                                                                     ▲  integrated vectorizer
  Managers → Managers group                                                                      │  (search identity → Azure OpenAI)
Copilot Studio agent ──(custom connector, user's Entra token)──► App Service auth ──► /api/ask ──┤ group_ids/any(g: search.in(...))
                                                                (Return401)          (Python)    └► Azure OpenAI chat, keyless
```

- **Trim at retrieval.** Every chunk carries the Entra group IDs of its library. Every query carries
  `group_ids/any(g: search.in(g, '<caller groups>', ','))`, the security-filter pattern from the Azure AI Search docs.
  The field is `filterable: true, retrievable: false`.
- **Who is asking** comes from App Service authentication (`X-MS-CLIENT-PRINCIPAL`), which only reaches the code
  after Easy Auth validated a token for the API (`requireAuthentication`, `Return401`, allowed audience
  `api://<api client id>`).
- **Fail closed.** No principal → 401. Group overage → 403 with an actionable message. No groups → no search. A
  library without groups stops the ingestion. Only GUIDs go into the OData filter.
- **No permitted sources, no model call.** Citations are checked after generation: invented ones are removed, an
  answer without a valid citation is returned with `grounded: false`.
- **Keyless.** Azure OpenAI and Azure AI Search have local auth disabled; the function's identity has *Search Index
  Data Reader* and *Cognitive Services OpenAI User*; the search service's identity has *Cognitive Services OpenAI
  User* for the vectorizer.

| Path | What it is |
|---|---|
| [`src/function_app.py`](src/function_app.py) | `POST /api/ask` (Python v2): 401/403/400/422/503 mapping, logs who and how many tokens, never the question |
| [`src/copilot/identity.py`](src/copilot/identity.py) | Parse `X-MS-CLIENT-PRINCIPAL`: object id, name, groups; group-overage detection (`_claim_names`, `hasgroups`) |
| [`src/copilot/retrieval.py`](src/copilot/retrieval.py) | `security_filter()` (GUIDs only) + hybrid search with `VectorizableTextQuery` |
| [`src/copilot/grounding.py`](src/copilot/grounding.py) | System prompt, numbered `<source>` envelopes, citation check |
| [`src/copilot/answer.py`](src/copilot/answer.py) | `ask()`: retrieve → no sources? stop → chat completion (Azure OpenAI v1 endpoint, Entra token provider) → check; handles `finish_reason: content_filter` |
| [`indexer/graph_source.py`](indexer/graph_source.py) | Microsoft Graph over `httpx2`: site → library → files (folders, `@odata.nextLink`) → download (302 followed **without** our token) |
| [`indexer/chunking.py`](indexer/chunking.py), [`push.py`](indexer/push.py), [`cli.py`](indexer/cli.py) | Heading-aware chunks, documents with `group_ids` and embeddings, `mergeOrUpload`, `create-index` / `ingest` commands |
| [`indexer/libraries.json`](indexer/libraries.json) | Library → Entra group mapping (fictional ids) |
| [`index/policies-index.json`](index/policies-index.json) | Index: key, title, url, chunk, `content_vector` (1536, HNSW cosine), `group_ids`, Azure OpenAI vectorizer |
| [`connector/apiDefinition.swagger.json`](connector/apiDefinition.swagger.json) | Custom connector (OpenAPI 2.0), one operation `AskHrPolicies`, OAuth 2.0 |
| [`infra/main.bicep`](infra/main.bicep) | Azure OpenAI (gpt-5.4-mini + text-embedding-3-small, pinned), AI Search Basic, Flex Consumption app with `authsettingsV2`, 10 role assignments |
| [`data/policies/`](data/policies) | Four fictional Contoso documents, including an IT FAQ with a planted prompt-injection line |
| [`tests/`](tests) | 73 pytest tests |

## Test locally (no Azure, no tenant)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                       # 73 passed (about 3 s; test_bicep.py needs the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
```

[`tests/stubs.py`](tests/stubs.py) is one local HTTP server standing in for Azure AI Search (it **applies the
`search.in` group filter** to an in-memory index built from `data/policies`, and refuses unfiltered queries) and for
the Azure OpenAI v1 endpoint (chat replies come from a Python callable). The real `azure-search-documents` and
`openai` SDKs talk to it, so the tests prove, for example, that manager-only text never appears in an employee's
prompt, that no chat call happens when nothing permitted matches, and that the same question returns different
answers for different groups. Graph is tested with an `httpx2.MockTransport` (paging, folders, the 302 download).
`test_bicep.py` compiles the template and checks keys-off, pinned model versions, least-privilege roles and the
Easy Auth settings. `test_connector.py` checks the OpenAPI file against what the function really returns.

Tested with Python 3.13, `azure-search-documents 12.1.0`, `openai 3.57.0` (ships `httpx2`), `azure-functions 2.4.0`,
`azure-identity 1.27.0`, Bicep CLI 0.49.2.

## Deploy (needs an Azure subscription and a Microsoft 365 lab tenant)

The full runbook (app registrations, group claims, Graph permission, connector, Copilot Studio) is in
[`demo.md`](demo.md). The Azure part:

```bash
az deployment group create -g rg-mglab-copilot -f infra/main.bicep -p infra/main.bicepparam \
   -p apiClientId=<HR Copilot API app id> ingestPrincipalId=$(az ad signed-in-user show --query id -o tsv)
cd src && func azure functionapp publish <functionAppName> && cd ..
export SEARCH_ENDPOINT=... SEARCH_INDEX=hr-policies OPENAI_ENDPOINT=...      # deployment outputs
python indexer/cli.py create-index && python indexer/cli.py ingest
```

## What we learned / gotchas

- **Group overage.** Above 200 groups (JWT), Entra omits the `groups` claim and emits `_claim_names` (or `hasgroups`
  in the implicit flow). Searching with an empty list would either leak (if you dropped the filter) or silently find
  nothing. We return 403 and configure the API registration to emit only *groups assigned to the application*.
- **Built-in alternative.** Azure AI Search can ingest SharePoint permissions itself (SharePoint in Microsoft 365
  indexer with ACLs, generally available in REST API `2026-10-01`) and filter by the caller's Entra token. If your
  content is only SharePoint and that indexer fits, evaluate it first. We use the application-managed security filter
  because it works for any source and every rule is testable here; Learn is explicit that with this pattern *your
  application* must authenticate users, get trusted group values and apply the filter to every query.
- **The filter is a string.** Only validated GUIDs go into `search.in`; a group *name* or anything with a quote is
  rejected (`test_filter_refuses_anything_that_is_not_a_guid`).
- **`retrievable: false` is not security.** It keeps `group_ids` out of results; the filter on every query is what
  enforces access (Learn says the same).
- **Documents can contain instructions.** `data/policies/it-faq.md` has one. Sources go into `<source>` envelopes the
  chunk can't close, the system prompt says sources are data, and the Azure OpenAI guardrails offer *document attack
  detection* for content passed as documents. What the real model does with the planted line is recorded in the
  demo, not assumed.
- **Content filter shows up two ways:** HTTP 400 with code `content_filter` for a blocked prompt (→ 422 here), or
  HTTP 200 with `finish_reason: content_filter` for a filtered completion (→ a fixed message, `grounded: false`).
  Learn notes filtered calls can still be billed.
- **Graph downloads redirect.** `/content` answers 302 to a pre-authenticated URL; follow it without the bearer token.
- **Entra scope for Azure OpenAI:** `https://ai.azure.com/.default` (Learn's troubleshooting page). The OpenAI SDK
  accepts the token provider as `api_key` and calls it per request (asserted in `test_answer_with_citations`).
- **Custom connectors take OpenAPI 2.0 only**, under 1 MB, and use the *top* security definition. In Copilot Studio,
  connector tools use the end user's credentials by default, which is what makes per-user trimming work.
- **Search keys off means roles for everyone,** including you: creating the index needs *Search Service
  Contributor*, pushing documents *Search Index Data Contributor*; the Bicep assigns both to `ingestPrincipalId`.
- **Not verified in the lab yet (needs tenant):** the exact claim names App Service puts in `X-MS-CLIENT-PRINCIPAL`
  for `groups` and `oid` (the code accepts both the short and the mapped names); availability of
  `gpt-5.4-mini 2026-03-17` as Data Zone Standard in Sweden Central; the Graph calls with a Sites.Selected identity;
  the connector's OAuth configuration (done in the portal, see demo.md).

## References

- [Security filters for trimming results (`search.in`)](https://learn.microsoft.com/azure/search/search-security-trimming-for-azure-search) · [`search.in` function](https://learn.microsoft.com/azure/search/search-query-odata-search-in-function)
- [Document-level access control options, incl. SharePoint ACLs (GA in 2026-10-01)](https://learn.microsoft.com/azure/search/search-security-best-practices#implement-document-level-access-control)
- [Azure OpenAI vectorizer](https://learn.microsoft.com/azure/search/vector-search-vectorizer-azure-open-ai) · [Configure a vectorizer (troubleshooting: OpenAI User role for the search identity)](https://learn.microsoft.com/azure/search/vector-search-how-to-configure-vectorizer#troubleshooting) · [Vector fields](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index#add-a-vector-field-to-the-fields-collection)
- [Azure AI Search roles](https://learn.microsoft.com/azure/search/search-security-rbac#built-in-roles) · [Azure built-in roles (AI + machine learning)](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#ai--machine-learning)
- [Azure OpenAI v1 endpoint with Entra ID (Python)](https://learn.microsoft.com/azure/foundry/openai/supported-languages?pivots=programming-language-python#authentication) · [Troubleshoot HTTP errors (scope, content_filter)](https://learn.microsoft.com/azure/foundry/openai/how-to/troubleshoot-errors) · [Content filtering behaviour](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter#scenario-details)
- [Model retirement schedule (gpt-5.4-mini, text-embedding-3-small)](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule)
- [App Service authentication: user claims and `X-MS-CLIENT-PRINCIPAL`](https://learn.microsoft.com/azure/app-service/configure-authentication-user-identities) · [Microsoft Entra provider, authorize requests](https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#authorize-requests)
- [Group claims and overage](https://learn.microsoft.com/security/zero-trust/develop/configure-tokens-group-claims-app-roles#group-overages) · [ID token overage claim](https://learn.microsoft.com/entra/identity-platform/id-token-claims-reference#groups-overage-claim)
- [Graph: list children](https://learn.microsoft.com/graph/api/driveitem-list-children?view=graph-rest-1.0) · [download content (302)](https://learn.microsoft.com/graph/api/driveitem-get-content?view=graph-rest-1.0) · [Selected permissions](https://learn.microsoft.com/graph/permissions-selected-overview)
- [Custom connector from an OpenAPI definition (2.0, 1 MB)](https://learn.microsoft.com/connectors/custom-connectors/define-openapi-definition#prerequisites) · [Connectors as tools in Copilot Studio](https://learn.microsoft.com/microsoft-copilot-studio/advanced-connectors) · [User authentication for tools](https://learn.microsoft.com/microsoft-copilot-studio/configure-enduser-authentication)
- [Flex Consumption with Bicep](https://learn.microsoft.com/azure/azure-functions/functions-create-first-function-bicep?pivots=programming-language-python)
- Blog: [Enterprise AI Copilot — Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-01-19-enterprise-ai-copilot-azure-openai-power-platform-sharepoint-integration/)
