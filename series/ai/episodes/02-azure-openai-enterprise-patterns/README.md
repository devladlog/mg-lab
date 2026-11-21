# DEVLADLOG AI #2 — Azure OpenAI enterprise patterns: an AI gateway, keyless end to end

One model deployment is a demo. Ten teams sharing it is a platform problem: who used which tokens, what happens
when one app burns the quota, what happens when a region throttles, and where the keys are. This episode builds the
pattern Microsoft documents as the **AI gateway in Azure API Management**, as Bicep, plus the client code that
behaves well behind it.

```
app ──(APIM subscription key, per team)──► API Management Basic v2 ──(managed identity)──► Azure OpenAI, primary region
                                            · llm-token-limit per team                  └─► Azure OpenAI, secondary region
                                            · llm-emit-token-metric → App Insights          (priority pool + circuit breaker)
```

- **No keys to Azure OpenAI anywhere.** Both accounts have `disableLocalAuth: true`. The gateway's system-assigned
  managed identity has **Cognitive Services OpenAI User**; apps never get a role on the model.
- **One APIM subscription per team** (`hr-bot`, `sales-copilot`): one revocable key and one token counter each.
  Over 2,000 tokens per minute → `429` + `Retry-After`; over the monthly quota → `403`.
- **Token metrics** per subscription and API go to Application Insights (`llm-emit-token-metric`).
- **Regional resilience**: two accounts in two regions behind a backend **pool** (priority 1 / priority 2). Each backend
  has a **circuit breaker** on 429 and 5xx that honours `Retry-After`.
- **Data residency**: deployment type `DataZoneStandard` (processing stays inside the data zone of the resource, EU
  for EU regions) instead of `GlobalStandard`.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Log Analytics + App Insights, API Management Basic v2 (system identity), logger + diagnostics, two backends with circuit breakers, priority pool, the `aoai` API (v1 chat completions + responses), one subscription per team |
| [`infra/modules/openai-account.bicep`](infra/modules/openai-account.bicep) | Azure OpenAI account (custom subdomain, key auth disabled), pinned model deployment, role assignments with `principalType` |
| [`infra/policies/aoai-api.xml`](infra/policies/aoai-api.xml) | API policy: token limit + quota, token metrics, drop caller credentials, managed identity to the backend, route to the pool, one gateway retry |
| [`infra/main.bicepparam`](infra/main.bicepparam) | Lab parameters (Sweden Central + Germany West Central, gpt-5-mini 2025-08-07) |
| [`src/aoai_gateway/client.py`](src/aoai_gateway/client.py) | OpenAI client pointed at the gateway (`/aoai/openai/v1/`), subscription key in the `api-key` header |
| [`src/aoai_gateway/errors.py`](src/aoai_gateway/errors.py) | `classify()`: 429 throttled · 403 quota exhausted · 400 `content_filter` · 503 no healthy backend · … |
| [`src/aoai_gateway/usage.py`](src/aoai_gateway/usage.py) | Per-feature token ledger from `usage` + the gateway's `x-gateway-*` headers; `low_budget()` to slow down before a 429 |
| [`src/aoai_gateway/smoke.py`](src/aoai_gateway/smoke.py) | Burst test through the gateway (watch the budget drain, the 429 and its Retry-After) |
| [`tests/`](tests) | 37 pytest tests: policy rules, compiled ARM checks, error classification, ledger, real OpenAI SDK against a local gateway stub |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q            # 37 passed (test_bicep.py needs the Bicep CLI; it's skipped otherwise)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
```

`test_bicep.py` compiles `main.bicep` and asserts on the ARM output: both accounts keyless with a custom subdomain,
model version pinned (`NoAutoUpgrade`), role = Cognitive Services OpenAI User with `principalType`, gateway Basic v2
with a system identity, breakers with `acceptRetryAfter` on 429, pool priorities 1/2, `api-key` subscription header,
custom metrics on. `test_policy.py` checks the policy XML against the reference pages (required attributes, at most
five metric dimensions, caller credentials removed before the backend, limits before routing).
Tested with Bicep CLI 0.49.2, `openai 3.57.0`, Python 3.13.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-aoai -l swedencentral
az deployment group create -g rg-mglab-aoai -f infra/main.bicep -p infra/main.bicepparam
# when it finishes, in the portal: APIM → Subscriptions → hr-bot → Show/hide keys
export APIM_GATEWAY_URL=https://<apim-name>.azure-api.net
export APIM_SUBSCRIPTION_KEY=<hr-bot primary key>
PYTHONPATH=src python -m aoai_gateway.smoke --deployment chat --requests 12
```

## What we learned / gotchas

- **Two retry layers multiply.** The OpenAI SDK retries 429/5xx twice by default; a gateway `retry` of 2 behind it
  turns one call into up to nine backend calls. Retry in one place: here the gateway does one fast retry (to land on
  the other pool member) and production clients keep the SDK default without adding their own loop.
  `test_sdk_retry_on_top_of_gateway_multiplies_calls` shows one logical call becoming three HTTP calls.
- **An Azure OpenAI 429 can carry a very long `Retry-After`.** Learn's caution on backends: use a circuit breaker on
  429 with `acceptRetryAfter`, so the gateway stops hammering that region and the pool moves on.
- **429 vs 403 mean different things.** 429 = rate (wait and retry); 403 = the token quota for the period is gone
  (retrying is pointless — alert the owner). `classify()` keeps that distinction in code.
- **Never forward the caller's credentials.** The SDK always sends `Authorization: Bearer <api_key>`; the policy
  deletes the `api-key` header and overrides `Authorization` with the gateway's managed-identity token.
- **Set `principalType` on role assignments** for a managed identity created in the same deployment, or the
  assignment can fail with `PrincipalNotFound` while the identity replicates.
- **Anyone who can edit APIM policies can act as the gateway's identity.** Learn calls this out for
  `authentication-managed-identity`; keep the identity's roles minimal and policy editing restricted.
- **Token counters are per gateway**, and with `estimate-prompt-tokens="false"` a request that goes over the limit is
  still sent; the next ones are blocked. Concurrent requests can briefly exceed the limit.
- **Not done here (lab scope):** network isolation. Basic v2 has no VNet integration; for private endpoints on the
  accounts with `publicNetworkAccess: Disabled`, use Standard v2 (outbound VNet integration) or Premium v2.
- **Needs tenant verification:** the `aoai` API is defined in Bicep as a plain HTTP API with two operations. The
  `llm-*` policies are documented for LLM APIs that follow the OpenAI Chat Completions/Responses schema; if the
  portal rejects them on this API, import the API with the portal's *Microsoft Foundry* wizard (*Azure OpenAI v1*
  compatibility) and apply the same `aoai-api.xml`.

## References

- [AI gateway in Azure API Management](https://learn.microsoft.com/azure/api-management/genai-gateway-capabilities)
- [llm-token-limit policy](https://learn.microsoft.com/azure/api-management/llm-token-limit-policy) · [llm-emit-token-metric policy](https://learn.microsoft.com/azure/api-management/llm-emit-token-metric-policy)
- [Authenticate and authorize access to LLM APIs (managed identity)](https://learn.microsoft.com/azure/api-management/api-management-authenticate-authorize-ai-apis) · [authentication-managed-identity](https://learn.microsoft.com/azure/api-management/authentication-managed-identity-policy)
- [Backends: load-balanced pool and circuit breaker](https://learn.microsoft.com/azure/api-management/backends) · [retry policy](https://learn.microsoft.com/azure/api-management/retry-policy)
- [Application Insights logger (Bicep)](https://learn.microsoft.com/azure/api-management/api-management-howto-app-insights)
- [API Management v2 tiers — networking](https://learn.microsoft.com/azure/api-management/v2-service-tiers-overview#networking-options)
- [Azure built-in roles — Cognitive Services OpenAI User](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#ai--machine-learning)
- [Bicep role assignments and principalType](https://learn.microsoft.com/azure/azure-resource-manager/bicep/scenarios-rbac#role-assignments)
- [Deployment types (Global, Data Zone, Standard)](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types)
- [Azure OpenAI quota and rate limits (SDK retries)](https://learn.microsoft.com/azure/foundry/openai/how-to/quota)
- [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule)
- Blog: [Azure OpenAI Enterprise — Complete Guide](https://www.devladlog.com/articles/ai/2026-06-03-azure-openai-enterprise-complete-guide-2026/)
