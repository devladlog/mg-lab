# DEVLADLOG Power Automate #4: Calling a REST API that pages, throttles and fails

A **Users without a manager** cloud flow that calls **Microsoft Graph with the HTTP action**, and the local
material to prove it handles paging, throttling, outages and secrets **before it touches the tenant**.

Why: in episode 2, a requester with no manager in Entra makes the approval fall back to the purchasing team. Every
Monday 06:30 (Lisbon) this flow lists the enabled users without a manager and emails purchasing.

- **Auth:** app registration with the Graph **User.Read.All** application permission; the HTTP action uses
  **Active Directory OAuth** (client credentials). The client secret is a **secret environment variable backed by
  Azure Key Vault**, read at run time with Dataverse *Perform an unbound action* →
  `RetrieveEnvironmentVariableSecretValue` (**Secure outputs**); the HTTP action has **Secure inputs**.
- **Paging:** `GET /v1.0/users?$select=...&$expand=manager($select=id,displayName)&$top=<page size>`, then a
  **Do until** loop follows `@odata.nextLink` as an opaque URL until it's gone (`limit.count` 100, `PT1H`).
  Each page is filtered (enabled, no manager) and merged with `union()`.
- **Retries:** explicit exponential policy (4 retries from `PT10S`, `PT5S`–`PT2M`). 408/429/5xx are retried,
  `Retry-After` is honoured, other 4xx fail at once.
- **Failure:** a failed page stops the loop, records Graph's status and message, joins the branches (`Page_done`),
  emails `automation-admins@contoso.com` and **terminates the run as Failed**. No partial report.
- All settings are **environment variables** in the solution (authority, tenant, Graph base URL, client ID, page
  size, client secret), which is also what lets the tests point the same definition at a local server.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `DirectoryChecks` (`pac solution unpack` layout): 1 flow, 2 connection references (Dataverse, Outlook), 6 environment variable definitions |
| [`src/solution/Workflows/Userswithoutamanager-…401.json`](src/solution/Workflows) | The flow definition |
| [`src/mockgraph/`](src/mockgraph) | Local stand-in for the token endpoint and `GET /v1.0/users` (paging with `$skiptoken`, `$expand=manager`, `$top` 1–999, no `$skip`, 401 without a bearer token, fault injection for 429/503). Listens on 127.0.0.1 only. `python -m mockgraph` |
| [`src/flowkit/`](src/flowkit) | Harness from episodes 1–3, **extended for this episode**: real HTTP execution against local servers ([`httpcall.py`](src/flowkit/httpcall.py): Active Directory OAuth / Basic / Raw, retry policies, `Retry-After`), **Do until**, **secure inputs/outputs** masking, per-iteration run history, lint rules for retry limits, hard-coded credentials, missing Secure inputs/outputs, Until limits, plain `http://`; the "skipped last action" rule now follows skips down the runAfter chain |
| [`src/samples/`](src/samples) | `directory.json` (7 fictional users: disabled account, new joiner without a manager...), `params-local.json` and `mocks-local.json` for the CLI demo |
| [`tests/`](tests) | 27 pytest tests: paging, retries and errors, secrets, gotchas, lint, `pac solution pack` |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ and pytest (no other packages). `pac` is optional; the pack test is skipped without it.

```bash
cd series/power-automate/episodes/04-http-connector-rest-api-patterns
python -m pytest                       # 27 passed in ~10 s (each test starts and stops its own local server)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m mockgraph --port 8765 --throttle-page 2 &        # local Graph stand-in; page 2 answers 429 once
python -m flowkit run solution/Workflows/*.json --params samples/params-local.json --mocks samples/mocks-local.json
kill %1
pac solution pack --zipfile ../out/DirectoryChecks.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `27 passed in 10.27s`. The CLI run prints `Get_all_pages Succeeded
(4 iterations)`, `retried Get_users_page: 429 (waited 2s), 200`, `Run: Succeeded`. `pac solution pack` then
`pac solution unpack` reproduces `src/solution/` byte for byte.

The connector actions (Dataverse secret retrieval, Outlook emails) are mocked; **the HTTP action really runs**:
flowkit requests a token from the local token endpoint and calls the local `/v1.0/users` over HTTP, page after
page. flowkit refuses any host other than 127.0.0.1/localhost, so a test can't reach a real service.

## How the material was made, and what still needs the tenant

The definition was written from the Logic Apps workflow schema (HTTP action, `retryPolicy`, `ActiveDirectoryOAuth`,
`runtimeConfiguration.secureData`, Until `limit`) and the Graph docs (List users, paging, List manager), packed and
unpacked with `pac`, and run against the local stand-in. **Needs tenant:** the app registration with admin consent,
the Key Vault secret and the secret environment variable, a real run against Graph, and the export (demo.md).

## What we learned / gotchas

- **The default retry policy is very patient.** Power Automate's default for Medium/High profiles sends "up to 12
  retries at exponentially increasing intervals, which scale by seven (7) seconds up to an interval of approximately
  1 hour" (Low: up to two retries, scaling by 5 minutes). Against a dead API that's hours before anyone knows.
  Set an explicit policy; the linter warns when there is none (`test_without_a_retry_policy_an_outage_takes_hours_to_surface`).
- **Only 408, 429 and 5xx are retried**; `Retry-After` sets the wait. A 400 or a wrong secret fails at once
  (`test_a_400_is_not_retried`, `test_a_wrong_secret_fails_at_the_token_and_never_calls_graph`).
- **Use `@odata.nextLink` as an opaque URL.** Graph says to use the entire URL and not to extract `$skiptoken`;
  `/users` doesn't support `$skip` at all (`test_rebuilding_the_next_page_url_with_skip_breaks`). Custom headers such
  as `ConsistencyLevel` aren't included in later page requests by default; set them on every call if you need them.
- **Pagination setting vs. a loop.** The HTTP action's *Pagination* setting follows `nextLink`/`@odata.nextLink` by
  itself (paginated items: 5,000 for Low, 100,000 for others). We use a Do until loop to process each page as it
  arrives and to stop cleanly on a failed page. Either way, every page request counts as an action run.
- **Until defaults to 60 iterations** (maximum 5,000). Set `limit.count` on purpose; the linter warns when it's missing.
- **Episode 2's lesson inside a loop.** Without the `Page_done` join, a handled failure leaves `Set_next_link` skipped
  as the last action of its branch and the loop is marked Failed (`test_a_handled_failure_still_fails_the_loop_without_the_join`).
  The lint rule now follows skips down a chain of actions, not only direct dependents.
- **Secrets:** environment variables of type Secret reference Azure Key Vault and can't be picked from dynamic
  content; read them with `RetrieveEnvironmentVariableSecretValue` and turn on **Secure outputs**; turn on
  **Secure inputs** on the HTTP action. A test shows the secret appears in the run record if Secure inputs is off.
- **Graph facts we rely on:** List users default page 100, maximum 999; `$expand=manager` on the list; Get manager
  returns 404 when no manager is set (we avoid the per-user call entirely).

### What was not verified here

- **Designer conventions** we couldn't confirm on Learn: the Dataverse parameter key `item/EnvironmentVariableName`,
  the flow parameter names for environment variables (`"Graph base URL (cts_GraphBaseUrl)"` with
  `metadata.schemaName`), and the exact XML of `environmentvariabledefinition.xml` (type codes and `secretstore` values
  are from the Dataverse table reference: String `100000000`, Secret `100000005`, Azure Key Vault `0`). The export in
  demo.md step 7 replaces them with what the designer writes.
- How the engine fetches the OAuth token (flowkit uses a standard client-credentials POST to
  `{authority}/{tenant}/oauth2/v2.0/token`), the exact shape of the HTTP action's outputs when the token request fails,
  and the random interval the engine picks for exponential retries (flowkit's waits are deterministic: 10, 20, 40, 80 s).
- Whether Graph omits `manager` or returns it as null for users without a manager. The filter
  (`equals(item()?['manager']?['id'], null)`) handles both (`test_null_and_missing_manager_are_treated_the_same`).

## References

- [HTTP connectors in Power Automate (training: premium, authentication options)](https://learn.microsoft.com/training/modules/http-connectors/)
- [Call external HTTP or HTTPS endpoints (Retry-After, pagination, asynchronous pattern)](https://learn.microsoft.com/azure/connectors/connectors-native-http)
- [Handle workflow errors and exceptions (retry policies, 408/429/5xx)](https://learn.microsoft.com/azure/logic-apps/error-exception-handling)
- [Handle throttling problems (429)](https://learn.microsoft.com/azure/logic-apps/handle-throttling-problems-429-errors)
- [Secure access and data (ActiveDirectoryOAuth properties, secure inputs and outputs in code view)](https://learn.microsoft.com/azure/logic-apps/set-up-security-permissions)
- [Schema reference for triggers and actions (operation options, asynchronous pattern)](https://learn.microsoft.com/azure/logic-apps/logic-apps-workflow-actions-triggers)
- [Limits of automated, scheduled, and instant flows (default retry policy, retry limits, Until, paginated items, 120 s timeout)](https://learn.microsoft.com/power-automate/limits-and-config)
- [Use environment variables for Azure Key Vault secrets (RetrieveEnvironmentVariableSecretValue, secure outputs)](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables-azure-key-vault-secrets)
- [Environment Variable Definition table reference (type and secret store values)](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/environmentvariabledefinition)
- [Secure data used in cloud flows](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/use-secure-inputs-outputs-triggers) · [Use environment variables](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/use-environment-variables)
- [Add OAuth authentication for HTTP request triggers (Who can trigger the flow)](https://learn.microsoft.com/power-automate/oauth-authentication)
- [Microsoft Graph: List users (permissions, page sizes, no $skip)](https://learn.microsoft.com/graph/api/user-list) · [List manager](https://learn.microsoft.com/graph/api/user-list-manager) · [Paging](https://learn.microsoft.com/graph/paging) · [Best practices](https://learn.microsoft.com/graph/best-practices-concept)
- Blog: [HTTP Connector & REST API Patterns: Complete Guide](https://www.devladlog.com/articles/power-automate/2026-05-02-http-connector-patterns-complete-guide-2026/)
