# DEVLADLOG AI #5 — AI agents and orchestration: tools, a human approval, and a workflow

Episode 4 left Contoso finance with a **review queue**: invoices whose totals don't add up, a faded scan, an invoice
above the approval limit, a duplicate. This episode builds an **accounts-payable assistant** that works that queue
with **Microsoft Agent Framework** (Python, 1.x) on an **Azure OpenAI** `gpt-5-mini` deployment through the
**Responses API** — and puts two independent brakes on it: a person confirms every approval, and the code enforces
the policy again even after a "yes". Then two agents run as a **sequential workflow** (checker → writer), each with
only the tools and the context it needs.

```
"work the queue" ──► Agent (gpt-5-mini, Responses API, store=false, capped loop)
                       ├─ list_review_queue / get_invoice / lookup_policy   (run freely)
                       └─ approve_invoice  ── approval_mode="always_require" ──► person: y/N ──► InvoiceStore.approve()
                                                                                                 (policy in code)
                     AuditTrail middleware: one record per tool that actually ran

INV-2026-0142 ──► checker (get_invoice, lookup_policy) ──findings only──► writer (no tools) ──► outbox/…-draft.md (not sent)
```

- **Keyless**: Azure OpenAI with `disableLocalAuth: true` and a custom subdomain; the client gets an Entra ID token
  from `DefaultAzureCredential` (scope `https://cognitiveservices.azure.com/.default`). Your user needs
  **Cognitive Services OpenAI User**, nothing more.
- **Human in the loop**: `@tool(approval_mode="always_require")` makes the run return `user_input_requests` instead of
  executing; `run_with_approvals()` shows name + arguments, sends `to_function_approval_response(yes/no)` and resumes
  in the **same session** (the framework binds approvals to pending requests in that session).
- **Policy in code**: `InvoiceStore.approve()` refuses arithmetic mismatches, totals above EUR 5,000, new suppliers,
  rejected invoices and empty notes — whatever the model or the human said. Approval is idempotent.
- **Bounded loop**: `max_iterations` 8 (default 40), `max_function_calls` 16 and `max_duration_seconds` 120 (both
  unlimited by default), `allow_concurrent_invocation` off because the tools share state.
- **No server-side conversation state**: `store=False`; the session keeps the history and the framework replays it
  (with encrypted reasoning items) instead of chaining `previous_response_id`.
- **Least privilege per agent**: the workflow's writer has no tools and receives only the checker's final text,
  through a custom `context_filter` (see the gotcha below).

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Azure OpenAI (S0, custom subdomain, keys off), `chat` = gpt-5-mini 2025-08-07 DataZoneStandard, pinned; Cognitive Services OpenAI User for the developer |
| [`src/apagent/store.py`](src/apagent/store.py) | `InvoiceStore` (queue, get, `approve()` with the policy rules), policy loader and a tiny section lookup |
| [`src/apagent/tools.py`](src/apagent/tools.py) | Four Agent Framework function tools bound to one store; `approve_invoice` requires approval, max 5 invocations |
| [`src/apagent/audit.py`](src/apagent/audit.py) | `AuditTrail` function middleware: tool, arguments, outcome (ok / refused / error), ms; optional JSON lines file |
| [`src/apagent/agent.py`](src/apagent/agent.py) | `make_client()` (keyless, limits), `build_agent()` (instructions, `store=False`), `run_with_approvals()` |
| [`src/apagent/run.py`](src/apagent/run.py) | CLI: works the queue, asks `Approve? [y/N]` on stdin, prints answer, audit table, queue, tokens |
| [`src/apagent/pipeline.py`](src/apagent/pipeline.py) | `SequentialBuilder` checker → writer, `findings_only` context filter, draft saved to `outbox/` marked "not sent" |
| [`data/`](data) | Fictional review queue (4 invoices, same suppliers as episode 4) and a fictional AP policy |
| [`tests/`](tests) | 27 pytest tests (below) |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q            # 27 passed (test_bicep.py is skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
```

What the tests cover:
- `test_agent_loop.py` runs the **real Agent Framework agent** (`OpenAIChatClient`, real `openai` SDK underneath)
  against a local stub of `POST /openai/v1/responses` that replays scripted `function_call` / `message` items:
  bearer token from the credential and no `api-key`, `store: false` and no `previous_response_id`, the four tool
  schemas; read tools run automatically and the approval-required call pauses the run; a declined call never
  executes (the model is told it was rejected); a human "yes" on an over-limit invoice is still refused by the
  store; a model that calls tools forever is stopped by the limits; an unknown tool name is answered with an error;
  an approval replayed into another session is ignored; the CLI flow with `y` on stdin.
- `test_pipeline.py`: checker gets only `get_invoice` + `lookup_policy`, writer gets no tools and exactly one
  user message with the findings; and a test that proves `chain_only_agent_responses=True` alone **would** pass
  the raw tool results to the writer.
- `test_store.py`: every policy rule, idempotency, copies not references, policy parsing.
- `test_bicep.py`: keyless account, pinned model, single role with `principalType`, params file compiles.

Tested with Python 3.13, `agent-framework-core 1.26.0`, `agent-framework-openai 1.18.2`,
`agent-framework-orchestrations 1.4.2`, `openai 3.57.0`, `azure-identity 1.27.0`, Bicep CLI as installed in the
build container.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-05 -l swedencentral
az deployment group create -g rg-mglab-ai-05 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export AOAI=https://<name>.openai.azure.com
PYTHONPATH=src python -m apagent.run --endpoint $AOAI --deployment chat --audit audit/run.jsonl
PYTHONPATH=src python -m apagent.pipeline INV-2026-0142 --endpoint $AOAI --deployment chat
```

`--approve all|none` answers every approval without asking (dry runs); the default asks on stdin.

## What we learned / gotchas

- **`chain_only_agent_responses=True` is not "only the answer".** In a `SequentialBuilder`, an agent's response
  messages include its tool calls and tool results, so the next agent receives the raw invoice JSON. If the next
  agent shouldn't see tool data, wrap it in `AgentExecutor(..., context_mode="custom", context_filter=...)`.
  `test_chain_only_agent_responses_alone_would_leak_tool_results` shows the leak; `findings_only()` closes it.
- **Defaults are generous.** Learn: `max_iterations` defaults to 40 model round trips; `max_function_calls` and
  `max_duration_seconds` default to unlimited, and the limits are checked after each batch of tool calls (a batch
  can overshoot). Set all three. Time spent waiting for approval counts toward the duration limit.
- **Approvals are bound to the session.** A "yes" sent into a different `AgentSession` is dropped with a warning
  (`Ignored an approval response…`); in 1.26 the follow-up `run()` then raises
  `ChatClientInvalidRequestException` because nothing is left to send. Reuse the session for the approval round
  trip; Learn warns that turning binding off lets a replayed or fabricated response approve a privileged call.
- **A declined call still reaches the model** as a tool result ("Tool call invocation was rejected by user").
  The instructions tell the agent not to retry; the store's rules don't depend on it obeying.
- **A human "yes" is not a control on its own.** The tool re-checks the policy; `test_human_yes_does_not_override_the_policy_in_code`
  approves an over-limit invoice and the store still refuses.
- **Without `store=False` the client chains `previous_response_id`**, i.e. the conversation lives in the service
  (Learn: response data is retained for 30 days by default). With `store=False` the framework replays the history
  and asks for `reasoning.encrypted_content`. Learn also notes `store=false` is not a blanket zero-retention
  guarantee; see the data-privacy page.
- **Tool results arrive in middleware as a list of `Content` items**, not as the string the function returned;
  `AuditTrail` joins their text before parsing.
- **Routing is explicit.** The generic `OpenAIChatClient` stays on OpenAI when `OPENAI_API_KEY` is set; pass
  `azure_endpoint=` and `credential=` (as `make_client()` does) to be sure you're on Azure. It then calls
  `{endpoint}/openai/v1/responses` with `api-version=preview` (the value the v1 preview reference documents).
- **Function calls run concurrently by default.** Our tools share one store, so `allow_concurrent_invocation` is off.
- **Agent or workflow?** Learn's rule of thumb: agents for open-ended, tool-choosing tasks; workflows for known steps
  or several agents; and "if you can write a function to handle the task, do that instead".

## References

- [Microsoft Agent Framework overview](https://learn.microsoft.com/agent-framework/overview/) — successor to Semantic Kernel and AutoGen; agents vs workflows
- [Using function tools with an agent](https://learn.microsoft.com/agent-framework/agents/tools/function-tools?pivots=programming-language-python) — limits, concurrent invocation, error details
- [Function tools with human-in-the-loop approvals](https://learn.microsoft.com/agent-framework/agents/tools/tool-approval?pivots=programming-language-python) — `approval_mode`, `user_input_requests`, approval binding
- [FunctionInvocationConfiguration (Python API)](https://learn.microsoft.com/python/api/agent-framework-core/agent_framework.functioninvocationconfiguration?view=agent-framework-python-latest) — `max_iterations` default 40
- [Agent middleware](https://learn.microsoft.com/agent-framework/concepts/agents/middleware/defining-middleware?pivots=programming-language-python)
- [Sequential orchestration](https://learn.microsoft.com/agent-framework/workflows/orchestrations/sequential?pivots=programming-language-python) and [Agent Executor — context modes](https://learn.microsoft.com/agent-framework/concepts/workflows/advanced/agent-executor?pivots=programming-language-python)
- [OpenAI / Azure OpenAI provider for Agent Framework (Python)](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/openai) and [Python 2026 significant changes](https://learn.microsoft.com/agent-framework/support/upgrade/python-2026-significant-changes)
- [Use the Azure OpenAI Responses API](https://learn.microsoft.com/azure/foundry/openai/how-to/responses) — function calling, 30-day retention, encrypted reasoning with `store=false`, supported models (gpt-5-mini 2025-08-07)
- [Foundry Models sold by Azure — GPT-5](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#gpt-5) — gpt-5-mini: Responses API, functions and tools
- [Azure OpenAI v1 API](https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle) and [v1 preview reference (Create response)](https://learn.microsoft.com/azure/ai-foundry/openai/reference-preview-latest#create-response)
- [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule) — gpt-5-mini 2025-08-07 (checked for this series on 21 Nov 2026: retirement 2027-07-13)
- Blog: [AI Agents & Orchestration — Complete Guide](https://www.devladlog.com/articles/ai/2026-05-02-ai-agents-orchestration-complete-guide-2026/)
