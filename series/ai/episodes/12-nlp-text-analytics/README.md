# DEVLADLOG AI #12 — NLP and text analytics: analyse the tickets, keep the people out of it

Blog guide: [NLP and Text Analytics: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-03-05-nlp-text-analytics-complete-guide-2025/)

Episode 11 built a chatbot, which means the Contoso Porto service desk now also has a growing pile of **free text**:
tickets and conversations in English and Portuguese, full of names, phone numbers and e-mail addresses. This episode reads
that text with **Azure Language** (the preconfigured features: language detection, PII detection, sentiment analysis with
opinion mining, key phrases, named entities) from Python, keyless, and enforces one rule in code: **the analysis never
sees the personal data**. It ends in a Markdown report, a next step per ticket, and a gate that fails if any planted
personal string survives.

```
ticket text ──► split_text (<= 5,120 chars) ──► detect language (first chunk) ──► PII redaction (service, per language)
                                                                                      │ error → ticket BLOCKED, raw text goes nowhere else
                                                                                      ▼
                                                              local backstop (CON-12345 badge ids) ──► redacted text
                                                                                      ▼
                                           sentiment + opinion mining · key phrases · entities  (batched by each feature's limit)
                                                                                      ▼
                                   merge chunks ──► route (manual-review / translate-first / priority-review / feedback-log / standard)
                                                                                      ▼
                                          report.md (aggregates only) · evaluate: leaks, language, sentiment ──► exit 0 / 1
```

| Question | Answer in this episode |
|---|---|
| What are the limits? | `limits.py`, from Learn: 5,120 characters per document (synchronous); documents per request 1,000 for language detection, 10 for sentiment and key phrases, 5 for entities and PII; 1 MB per request |
| What if a ticket is too long? | `split_text` cuts on paragraphs, then sentences, then hard; every chunk is a document; sentiment is merged by our own stated rule (length-weighted, `mixed` if chunks disagree) |
| What does it cost? | Learn: a text record is 1,000 characters; the free tier gives 5,000 records per month. `python -m ticketnlp limits` prints a worst-case estimate (the five features summed) for a file, with no Azure call |
| In what order? | Language, then PII, then a local backstop for Contoso-only identifiers, then analytics on the **redacted** text. If redaction fails for a ticket, nothing else runs on its raw text |
| What does opinion mining add? | Each opinion is linked to a target (the VPN, the battery): `analyze_sentiment(show_opinion_mining=True)` gives the aspects the report ranks |
| Who may call it? | Keyless (`disableLocalAuth`), Entra ID against the custom subdomain, role **Cognitive Services Language Reader** (Learn lists the `analyze-text` data action in it; it is read-only on authoring) |
| How do we know redaction works? | `evaluate`: every case lists the personal strings planted in it; they are searched for in everything the pipeline outputs. One survivor fails the gate. `--compare` also runs on raw text to show what that leaks |

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Language resource (kind `TextAnalytics`, West Europe, **F0** by default, keys off, custom subdomain), Language Reader role for the developer |
| [`src/ticketnlp/limits.py`](src/ticketnlp/limits.py), [`cost.py`](src/ticketnlp/cost.py) | Documented limits, chunking, batching, text-record estimate |
| [`src/ticketnlp/analyzer.py`](src/ticketnlp/analyzer.py), [`client.py`](src/ticketnlp/client.py) | Batched wrapper over `azure-ai-textanalytics` with per-document errors; the Entra client |
| [`src/ticketnlp/pipeline.py`](src/ticketnlp/pipeline.py), [`backstop.py`](src/ticketnlp/backstop.py) | The ordered, fail-closed pipeline; local pattern redaction |
| [`src/ticketnlp/route.py`](src/ticketnlp/route.py), [`report.py`](src/ticketnlp/report.py) | Next-step rules with reasons; the aggregate-only Markdown report |
| [`src/ticketnlp/evaluate.py`](src/ticketnlp/evaluate.py), [`cli.py`](src/ticketnlp/cli.py) | Gate and scorecard; `python -m ticketnlp limits / show / analyze / evaluate` |
| [`data/tickets.json`](data/tickets.json) | 13 fictional tickets (en, pt, es), with the language, sentiment and planted personal strings we expect; includes a thread over the limit, an emoji case, a badge id, a mixed-language and a blank ticket |
| [`tests/`](tests) | 50 pytest tests |

Tested with Python 3.13, `azure-ai-textanalytics 5.4.0`, `azure-identity 1.27.0`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                                          # 50 passed
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep     # no warnings
PYTHONPATH=src python -m ticketnlp limits                          # no Azure call
```

What the tests cover: the **real SDK** sends its real requests (`POST <endpoint>/language/:analyze-text?api-version=2023-04-01`
with the Entra bearer token, scope `https://cognitiveservices.azure.com/.default`) through a stand-in transport, and a
rule-based fake answers in the service's response shape and enforces the limits Learn documents. The fake's "language",
"PII" and "sentiment" are keyword and regex lookups, so the tests prove the plumbing, **not** the accuracy of the service:
- `test_limits_analyzer.py`: Learn's numbers, record rounding, chunking (paragraph, sentence, hard cut; nothing lost;
  code points vs text elements), request shape and token scope, every feature batched by its own limit, an over-long document
  never sent, a document error isolated, a failed request raises, opinion-mining targets.
- `test_pipeline_route_report.py`: analytics only ever receive redacted text, call order, language passed on, uncertain
  language flagged, the backstop, long tickets chunked and merged, blank text skipped, **redaction failure fails closed**,
  routing order, the report contains no ticket text or personal data, the cost arithmetic.
- `test_evaluate_cli_bicep.py`: the gate passes with redaction and fails on raw text, on a PII miss, on wrong language
  and on a failing document; leak matching ignores case, spacing and phone formatting; CLI exit codes; the compiled Bicep
  (keyless, F0 default, Language Reader only, not Cognitive Services User).

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-12 -l westeurope
az deployment group create -g rg-mglab-ai-12 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export TICKETNLP_ENDPOINT=<languageEndpoint> PYTHONPATH=src
python -m ticketnlp show --id en-neg-vpn                       # one ticket, original next to redacted
python -m ticketnlp analyze --out build/report.md              # the report
python -m ticketnlp evaluate --compare ; echo $?               # 0 = gate passes, 1 = it does not
az group delete -n rg-mglab-ai-12 --yes
```

Needs the lab subscription: every result in `show`, `analyze` and `evaluate` is a real call. Nothing in this folder
claims a result the service has not produced; the numbers on screen come from the run recorded in `demo.md`.

## What we learned / gotchas

- **Redaction is detection.** The service removes what it recognises. Learn: the PII feature redacts **all detected**
  entities regardless of confidence, so the problem is never "too confident", it is "not detected". Entities not enabled by
  default for a language need `piiCategories` (Learn); the SDK has `categories_filter` and enum members such as
  `PT_TAX_IDENTIFICATION_NUMBER` and `PT_CITIZEN_CARD_NUMBER` (not exercised against the service here).
- **Redact before you analyse, not after.** On raw text, key phrases and entities repeat the names and e-mail addresses
  back to you; `--compare` shows it. And because a failed redaction blocks the ticket, an outage makes the pipeline slower
  and emptier, never leakier.
- **Your identifiers are yours.** The service cannot know that `CON-48213` is a badge number, so a local pattern pass
  (`backstop.py`) runs after it. It is a list you maintain, not a model.
- **Per-document limits are strict.** Learn: in a synchronous call a document over 5,120 characters is not processed and
  returns an invalid-document error; a request with too many documents is an HTTP 400. The code splits and batches
  first, and never sends an over-long document. Learn measures **text elements**, we count code points, which is never
  fewer, so a chunk that fits by our count fits by theirs.
- **Rate limits.** Learn: F0 and S0 allow 100 requests per second and 300 per minute, measured per feature. The SDK's
  retry policy handles `429`; a large backlog needs a queue and a slower pace, not a loop.
- **Pass the language.** If a language is not given, Learn says extraction defaults to English. The pipeline passes the
  detected language to every call, but when detection confidence is below 0.6 (our threshold) the ticket is flagged
  `language_uncertain` and routed to a person instead of being analysed as English by accident.
- **Mixed-language tickets are a real case.** "Hello team, o VPN voltou a falhar" has one language label; the service
  returns one answer per document. The scorecard leaves this case unlabelled on purpose.
- **Merging chunks is our rule.** A ticket over the limit becomes several documents; the service never sees it whole.
  We average the confidence scores weighted by length and call the ticket `mixed` if the chunk labels differ. That is a
  choice, written down, not something the service does.
- **Opinion mining is the useful part.** A negative label tells you little; a negative *target* tells you what to fix.
- **Estimating cost.** Learn: pricing is per text record of 1,000 characters, and the free tier is 5,000 records per month. We
  sum the five features in `limits` as a worst case; we did not verify whether features are billed together.
- **Language Reader vs Cognitive Services User.** Learn's role definition for Language Reader lists
  `Language/analyze-text/action` and read-only authoring, while Cognitive Services User has all data actions and can list keys.
  Least privilege says the first, but whether it is enough for this exact SDK call is for the demo to confirm (see `demo.md`).
- **F0 limits.** Learn's limits pages for the custom Language features say you may have one F0 Language resource per
  subscription. The Bicep file has a `skuName` parameter (`F0` or `S`) for that case; Learn says S also starts with 5,000
  free text records before charging.
- **Thirteen tickets are plumbing, not accuracy.** The sentiment labels are ours, one case moves a percentage by ten points,
  and the planted personal strings only test what we thought to plant. The scorecard is a template to run on your own
  anonymised tickets, many more.

Out of scope on purpose: summarisation, custom classification and custom NER (they need training or a different resource
setup), Text Analytics for health, and conversation PII. They are a next step, not part of this episode.

## References

- [Service limits for Azure Language](https://learn.microsoft.com/azure/ai-services/language-service/concepts/data-limits) — 5,120 characters, documents per request, text records, rate limits
- [Detect and redact PII in text](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/how-to/redact-text-pii) — redaction, `piiCategories`, all detected entities are redacted
- [Recognized PII entities](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/concepts/entity-categories) — categories including Portugal
- [Language support](https://learn.microsoft.com/azure/ai-services/language-service/concepts/language-support) and [PII language support](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/language-support)
- [Azure Language region support](https://learn.microsoft.com/azure/ai-services/language-service/concepts/regional-support) — data stays in the region
- [Azure Text Analytics client library for Python 5.4.0](https://learn.microsoft.com/python/api/overview/azure/ai-textanalytics-readme?view=azure-python) and [TextAnalyticsClient](https://learn.microsoft.com/python/api/azure-ai-textanalytics/azure.ai.textanalytics.textanalyticsclient?view=azure-python)
- [Authenticate requests to Foundry Tools](https://learn.microsoft.com/azure/ai-services/authentication) — Entra needs the custom subdomain; [Disable local authentication](https://learn.microsoft.com/azure/ai-services/disable-local-auth)
- [Cognitive Services Language Reader role](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#cognitive-services-language-reader)
- Blog: [NLP and Text Analytics: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-03-05-nlp-text-analytics-complete-guide-2025/)
