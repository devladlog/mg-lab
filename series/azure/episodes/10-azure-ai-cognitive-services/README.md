# DEVLADLOG Azure #10 — Azure AI & Cognitive Services: triage support tickets with Azure AI Language, no keys, free tier

Earlier episodes ran contoso's orders. This one reads what customers write about them. A small .NET 10 app takes support
tickets (fictional, in English, Portuguese, French and Spanish, one with a pasted card number, one with a bank account) and, for each:

1. **detects the language** (batch, up to 1,000 documents per request),
2. **detects and redacts personal data** (PII), passing the detected language per document, 5 documents per request,
3. **scores sentiment on the redacted text only** (10 documents per request), so the raw text goes to exactly one call,
4. **routes it** with plain, unit-tested rules: card/bank numbers → `security-review`, strongly negative → `escalate`, otherwise a queue per language.

And it counts the **text records** the run bills, against the free tier's 5,000 a month.

- **Free tier, no keys.** The Language resource is `F0` with `disableLocalAuth: true` and a custom subdomain (Entra ID needs one).
  The caller gets one role, **Cognitive Services Language Reader**, via `DefaultAzureCredential` (Azure CLI on the laptop,
  a managed identity in Azure). There is no `AzureKeyCredential` anywhere (a test greps for it)
- **The failure is part of the demo.** `deploy.sh` creates the resource with nobody allowed; the first `run.sh` fails with a
  hint; `deploy.sh --role` grants the role; the second run works. `rest-check.sh` shows a bearer token accepted and a key refused
- **Teardown purges.** Deleted AI resources are soft deleted; `teardown.sh` deletes the group and then purges the account

```
 tickets.json ─► LanguageDetection ─► PII (raw text, language per doc) ─► Sentiment (REDACTED text) ─► Router ─► route + usage line
                       │                       │                               │
                       └────────── TextAnalyticsClient + DefaultAzureCredential (bearer token, no key) ──► lang-triage-xxxx (F0)
```

| Path | What it is |
|---|---|
| [`src/SupportTriage`](src/SupportTriage) | .NET 10 console app: [`TicketTriage.cs`](src/SupportTriage/TicketTriage.cs) (pipeline), [`Limits.cs`](src/SupportTriage/Limits.cs) (documented limits, text records, chunking), [`Router.cs`](src/SupportTriage/Router.cs), [`UsageMeter.cs`](src/SupportTriage/UsageMeter.cs), [`Program.cs`](src/SupportTriage/Program.cs) (`--endpoint`, `--tickets`, `--dry-run`; exit 0 ok, 1 some ticket needs manual handling, 2 no endpoint, 3 service refused) |
| [`data/tickets.json`](data/tickets.json) | Seven fictional tickets (`contoso.example` addresses, a documentation IBAN, a test card number) |
| [`infra/main.bicep`](infra/main.bicep) | Language account (kind `TextAnalytics`, `F0`, key access off, subdomain) + optional role assignment |
| [`infra/deploy.sh`](infra/deploy.sh) | Checks there is no other F0 Language resource, creates the group, what-if, deploy; `--role` grants the role to the signed-in user |
| [`infra/run.sh`](infra/run.sh) / [`rest-check.sh`](infra/rest-check.sh) | Runs the app with the saved endpoint / the same service with `curl`: token accepted, key refused |
| [`infra/teardown.sh`](infra/teardown.sh) | `az group delete`, then `az cognitiveservices account purge` |
| [`tests/SupportTriage.Tests`](tests/SupportTriage.Tests) | 22 xUnit tests |
| [`tests/infra`](tests/infra) | 17 pytest tests |

## Build and test (here, no Azure needed)

```bash
dotnet test tests/SupportTriage.Tests -m:1
#   Passed!  - Failed: 0, Passed: 22, Skipped: 0, Total: 22
#   TicketTriageTests 7  the REAL SDK runs against a stand-in HTTP handler (tests only): bearer token and no key header, path and
#                        api-version 2023-04-01, batch sizes 5/10/1000 respected, sentiment requests contain no raw email or card,
#                        detected language sent per document, routes, over-limit document reported and not sent, usage = 21 records
#   LimitsRouterTests 13 text-record rounding, text elements vs UTF-16 units, chunking, sentiment threshold, sensitive categories win,
#                        language queues, sample data unique and under one text record each
#   ProgramTests 2       --dry-run estimate (21 records, 238 runs/month), no endpoint -> exit 2

python3 -m pytest tests/infra -q      # 17 passed
#   bicep lint clean; F0 + TextAnalytics + disableLocalAuth + custom subdomain; role id 7628b7b8-... (Language Reader), optional;
#   no keys in outputs; deploy.sh guards the one-F0 rule; teardown deletes then purges; rest-check body is valid JSON;
#   bash -n on all scripts; no AzureKeyCredential or key-like strings; script.yaml: header, 12-16 scenes, 750-900 words, 3 shorts,
#   every code line exists in this folder

dotnet run --project src/SupportTriage -c Release -- --dry-run
#   text records (estimate): 21 = language 7, pii 7, sentiment 7; that is 0.4 % of the free 5,000 a month, 238 such runs per month
```

Mutation checks done by hand: raising `PiiMaxDocuments` from 5 to 10 fails the batch-limit test; sending the raw text to the
sentiment call fails the "sentiment only sees redacted text" test.

Verified in this container: .NET SDK 10.0.115, `Azure.AI.TextAnalytics` 5.3.0, `Azure.Identity` 1.17.2, Bicep 0.49.2, pytest 9.1.1.

**Not run here (needs the lab subscription, see demo.md):** everything against the real service: the deployment, the role
assignment and its delay, the first-call failure and its exact status, real language/PII/sentiment results and the routes
they produce, `rest-check.sh`, `teardown.sh` (no `az` CLI here; `bash -n` only). **The stand-in service in the tests is a
keyword toy used only to test our batching, ordering and routing; it says nothing about the real models.** The JSON shapes it
returns were not checked against the live API beyond what the SDK accepts.

## Cost

| Item | Price | Note |
|---|---|---|
| Azure AI Language `F0` | 0 | 5,000 text records a month (Learn: service limits, quota tables); one F0 Language resource per subscription (Learn) |
| A run of the sample | 21 text records | 7 tickets x 3 features; each ticket is under 1,000 characters |
| Rate limit on F0 | 100 requests/s, 300/min | Learn: Language service limits |

Recording cost: **EUR 0**. Standard (S) tier prices were not checked: not used.

## What we learned / gotchas

- **Entra ID needs the custom subdomain, and the regional endpoint will not do.** Learn (Authenticate requests): "Regional
  endpoints do not support Microsoft Entra authentication". The template sets `customSubDomainName` to the account name.
- **Keys off means `disableLocalAuth: true`** (Learn: set it in Bicep/ARM). Samples and quickstarts that read a key from the portal
  will not work against this resource; that is the point.
- **Owner is not enough.** Creating the resource does not let you call its data plane: the deployment user still needs a role
  (Learn: Language Reader includes the data action `Language/analyze-text/action`). Learn: role assignments "may take up to five
  minutes to propagate". The exact status of the first failure was not observed here: demo.md says to record it.
- **Limits are per feature, in documents and text elements.** Learn: PII 5 documents, sentiment 10, language detection 1,000 per
  request; 5,120 characters per document for synchronous calls, measured with `StringInfo.LengthInTextElements`; a text record is
  1,000 characters and all billing and the free quota count records. A document over the limit returns an invalid-document error
  in a synchronous batch (others in the batch still process); we report it ourselves and never send it.
- **Every feature call is a billed record.** Three features per ticket means three records per ticket, not one: the meter shows it.
- **PII redaction only covers the categories you ask for.** Learn's transparency note: if you pass `piiCategories` only those are
  redacted, and with a locale default, categories of other locales can leak (a German driving licence in an `en-US` request).
  We use the defaults for the detected language and do not set `piiCategories`; for a real mixed-language inbox, review that choice.
  The same note recommends language detection first when the language is unknown, which the pipeline does.
- **Deleted is not gone.** Learn (recover or purge): a deleted resource's name cannot be reused for 48 hours unless purged; purging
  with Contributor needs the role at **subscription** level. With one F0 per subscription, a soft-deleted resource can block the
  next demo. `teardown.sh` purges. (Whether a soft-deleted F0 still counts against the one-per-subscription limit was not tested.)
- **Naming.** Learn's current pages call these services *Foundry Tools* (and the resource a *Foundry resource*); the ARM kind for
  Language is still `TextAnalytics`, and the older names (Cognitive Services, Azure AI services) are what people search for.
- **API versions.** The SDK 5.3.0 sends `api-version=2023-04-01` to `/language/:analyze-text` (seen in the tests). Learn's PII page
  also documents a newer preview (`2025-11-15-preview`) with `redactionPolicies` and `confidenceScoreThreshold`; not used here.

## References
- Blog: [Azure AI & Cognitive Services — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-12-azure-ai-cognitive-services-complete-guide-2026/)
- [Authenticate requests to Foundry Tools](https://learn.microsoft.com/azure/ai-services/authentication) (Entra ID, custom subdomain, regional endpoints) and [Disable local authentication](https://learn.microsoft.com/azure/ai-services/disable-local-auth)
- [Service limits for Azure Language](https://learn.microsoft.com/azure/ai-services/language-service/concepts/data-limits) (documents per request, characters, text records, rate limits) and [CLU limits](https://learn.microsoft.com/azure/ai-services/language-service/conversational-language-understanding/service-limits) (one F0 per subscription, 5,000 records)
- [PII detection overview](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/overview), [text PII](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/how-to/redact-text-pii), [.NET quickstart](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/quickstart), [transparency note](https://learn.microsoft.com/azure/foundry/responsible-ai/language-service/transparency-note-named-entity-recognition)
- [Text Analytics client library for .NET 5.3.0](https://learn.microsoft.com/dotnet/api/overview/azure/ai.textanalytics-readme)
- [Built-in roles: AI + machine learning](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#cognitive-services-language-reader) (Cognitive Services Language Reader, id `7628b7b8-a8b2-4cdc-b46f-e9b35248918e`)
- [Recover or purge deleted resources](https://learn.microsoft.com/azure/ai-services/recover-purge-resources), [`az cognitiveservices account purge`](https://learn.microsoft.com/cli/azure/cognitiveservices/account)
