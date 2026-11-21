# DEVLADLOG Dev Tools #8 — API testing with Postman: tests that can actually fail

The orders API from [episode 4](../04-docker-for-developers/) (the one [episode 5](../05-ci-cd-pipeline-setup/) ships) gets a
**Postman collection with real assertions**, a data-driven negative test, and a headless run that CI calls, plus three
small gates for the ways an API test run stays green while proving nothing.

```
 API (.NET 10) ── /openapi/v1.json ──► openapi.v1.json (committed snapshot = the contract)
                                            │ import into Postman: requests + examples
                                            ▼
 orders-api.postman_collection.json ── tests: status, strict JSON schema, chained ids, response time
        │            └─ Data-driven folder + data/invalid-orders.json (6 rows)
        ▼
 scripts/run-api-tests.sh ──► dotnet run (Production) ─► Newman ×2 ─► JUnit ─► junit_gate.py (did the tests run?)
        ▲                                                             collection_lint.py / openapi_coverage.py (before the run)
 .github/workflows/api-tests.yml  (one job, `api-tests`)
```

- **The API describes itself.** `Microsoft.AspNetCore.OpenApi` serves `/openapi/v1.json` (OpenAPI 3.1 on .NET 10); endpoints got names
  (`operationId`) and `Produces` metadata, `/healthz` a named type so its schema exists. `tools/export_openapi.py` saves the document;
  a test fails when the committed snapshot is not what the API generates today, so a contract change shows up in a pull request diff.
- **The collection is the test suite** (Collection v2.1 JSON, importable in Postman): health (and, after a deploy, the exact version
  from episode 5), create → read back (the id is chained through a collection variable), paging defaults and cap, 404s, validation problems
  as `application/problem+json`, a collection-level test that every response is fast, and a **Data-driven** folder run once per row of a data file.
- **Three gates** for green-but-empty runs: `collection_lint.py` (every request has its own tests and asserts a status, no hard-coded host,
  no credentials in exports), `openapi_coverage.py` (every documented operation **and every documented status code** has a request that
  asserts it), `junit_gate.py` (the run executed at least N assertions).
- **One script, same on a laptop and in CI**: `scripts/run-api-tests.sh` starts the API from source in *Production* mode on a free port (or
  tests one that's already running with `--no-start`: a container, a deployment), runs Newman twice, writes JUnit, applies the gate.

| Path | What it is |
|---|---|
| [`src/orders-app/api-tests/orders-api.postman_collection.json`](src/orders-app/api-tests/orders-api.postman_collection.json) | The collection: 4 folders, 10 requests, 31 assertions in one run + 24 in the data-driven run |
| [`src/orders-app/api-tests/environments/local.postman_environment.json`](src/orders-app/api-tests/environments/local.postman_environment.json) | `baseUrl`, `maxResponseMs`, `expectedVersion`. No secrets (the orders API has no auth) |
| [`src/orders-app/api-tests/data/invalid-orders.json`](src/orders-app/api-tests/data/invalid-orders.json) | Six invalid orders and the field each must be rejected for; values are JSON literals so `null` and `""` can be sent |
| [`src/orders-app/api-tests/openapi.v1.json`](src/orders-app/api-tests/openapi.v1.json) | Committed snapshot of the API's OpenAPI 3.1.1 document (without `servers`) |
| [`src/orders-app/api-tests/tools/collection_lint.py`](src/orders-app/api-tests/tools/collection_lint.py) | Static rules: `no-tests`, `no-status`, `hardcoded-host`, `secret`, `duplicate` |
| [`src/orders-app/api-tests/tools/openapi_coverage.py`](src/orders-app/api-tests/tools/openapi_coverage.py) | Operations and documented status codes vs requests and `to.have.status(...)` assertions; also reports requests for endpoints that no longer exist |
| [`src/orders-app/api-tests/tools/junit_gate.py`](src/orders-app/api-tests/tools/junit_gate.py) | Fails on failures, on fewer than `--min-tests` assertions, on skipped tests |
| [`src/orders-app/api-tests/tools/export_openapi.py`](src/orders-app/api-tests/tools/export_openapi.py) | Saves the running API's document as the snapshot |
| [`src/orders-app/scripts/run-api-tests.sh`](src/orders-app/scripts/run-api-tests.sh) | Start API (optional) → wait for `/healthz` → Newman ×2 → JUnit gate → stop API; exit status = any failure |
| [`src/orders-app/.github/workflows/api-tests.yml`](src/orders-app/.github/workflows/api-tests.yml) | `npm ci` (Newman pinned to 6.2.3 in the lock file) → lint → coverage → run → upload JUnit; actions pinned to commits |
| [`src/orders-app/src/Contoso.Orders.Api/`](src/orders-app/src/Contoso.Orders.Api/) | Episode 5's API plus OpenAPI (`AddOpenApi`, `MapOpenApi`, operation names, `Produces`, `Health` record); setting `OpenApi:Enabled` (default on) |
| [`src/orders-app/tests/`](src/orders-app/tests/) | Episode 5's xUnit tests plus two for the OpenAPI document (23 pass, 4 skip) |
| [`tests/`](tests/) | 45 pytest tests (below) |

## Run the tests

```bash
cd series/developer-tools/episodes/08-api-testing-with-postman
(cd src/orders-app/api-tests && npm ci --no-audit --no-fund)     # Newman 6.2.3 (the real runs need it)
(cd src/orders-app && dotnet test)                                # Passed! 23 passed, 4 skipped (SQL Server tests: no SQL Server here)
python3 -m pytest -q tests                                        # 45 passed (~50 s)
(cd src/orders-app && scripts/run-api-tests.sh)                   # the run CI does: 32 + 24 assertions, exit 0
rm -rf src/orders-app/api-tests/node_modules                      # keep the folder small
```

| Test file | What it proves |
|---|---|
| `test_tools.py` (24) | The committed collection and environment pass the lint, and each rule fires on a mutated copy (request without tests, test without a status check, hard-coded host, Bearer token, duplicate name, secret variable not of type `secret`); coverage passes today and fails for a new endpoint, a documented status nobody asserts, and a request for a removed endpoint; path matching (`{id}` vs `{{orderId}}`, `abc`, `:id`); the JUnit gate (failure, zero tests, too few, skipped, missing or broken file) |
| `test_workflow.py` (12) | Schema; one job named like its id; read-only token; every action pinned to the recorded commit with a version comment and every `with:` input present in that action's `action.yml`; no `${{ }}` inside `run:`; the script, npm scripts and directories it names exist; lint → coverage → run order; Newman pinned exactly in `package.json` and `package-lock.json`; reports uploaded when a test failed |
| `test_run_script.py` (9) | **Real runs** of the real API and Newman: the script end to end (32 + 24 assertions, six data iterations); `--no-start` against an API that is already running; the version check fails when the API reports another commit; the committed OpenAPI snapshot equals what the API generates now; **a regression** (`MaxPageSize` 100 → 1000 in a copy) fails exactly `cap: asking for 500 returns at most 100` and nothing else; a collection with no tests exits 0 in Newman and fails the gate; an unknown folder and an unreachable API exit 1; the data-driven folder fails loudly without its data file; reruns add fresh orders and don't depend on the seed |

**Not run here:** Postman itself (the desktop app: import, authoring, Collection Runner), the **Postman CLI**, GitHub-hosted runners, Docker. They
are recorded for real, see [demo.md](demo.md). The Postman CLI's postinstall downloads a binary; I didn't install it on the shared build machine, so
`postman collection run` is **not verified** here (flags below come from Postman's documentation only).

## What we learned / gotchas

- **Newman exits 0 for a collection with no tests.** Run with every `pm.test` removed: 9 requests, `assertions 0`, exit code 0. A pipeline that
  only checks the exit code is green on an empty suite. `junit_gate.py --min-tests` counts the assertions that ran, and `collection_lint.py`
  rejects a request with no tests of its own (the collection-level "fast enough" test doesn't count: it would still give every request one
  green assertion). An unknown `--folder` and an unreachable API do exit 1 (tested).
- **The JUnit report merged same-named tests across iterations.** Console: 24 assertions for six data rows; JUnit: 19, because the
  collection-level test had the same name in every iteration. A gate counting testcases would have been wrong in the *safe*-looking direction
  until the name carried `[iteration n]` (added only when `pm.info.iterationCount > 1`). Every `pm.test` in the data-driven folder includes the row's `case`.
- **Test the mode you ship.** The same bad-JSON `POST /orders` gives `400` with a 4 KB ProblemDetails naming `BadHttpRequestException` when the API runs in
  *Development* (what `dotnet run` with a launch profile does) and `400` with an **empty body** in *Production* (the container). The run script sets
  `ASPNETCORE_ENVIRONMENT=Production` and `--no-launch-profile`; the test only asserts the status because the body differs by design.
- **The generated schema is looser than the API you meant.** In the .NET 10 document every integer is `"type": ["integer","string"]` with a digit pattern,
  every `decimal` is `["number","string"]`. A test generated from that schema would accept `"id": "7"`. The collection carries a **hand-written strict schema**
  (`integer`, `minimum`, `additionalProperties: false`). Strictness is a choice: a new field then fails the schema test until someone updates it. Here that is
  the point (an accidental `Email` property shouldn't leave the API unnoticed); for a public API you may want it off.
- **OpenAPI coverage should include status codes.** `GET /orders/{id}` documents 200 and 404; a collection that only tests 200 "covers" the operation.
  `openapi_coverage.py` reads the `to.have.status(NNN)` calls and reports `documented but never asserted`.
- **`/orders/abc` is a 404, not a 400 or 500**, because of the `{id:int}` route constraint: no route matches. The collection pins that down.
- **A `trap … EXIT` handler's last command sets the script's exit status.** `[[ -n "$x" ]] && rm …` returned 1 when nothing had to be removed
  (`--no-start`), and the script exited 1 after a fully green run. The pytest run found it; the handler now ends with `return 0`.
- **Newman is in maintenance:** Postman's Newman page says *"Newman won't receive updates or fixes"* and tells you to *"replace Newman in your scripts and CI
  pipelines with the Postman CLI"*. We still use Newman here because it is open source, installs per project from npm, and I could run it in
  this environment; the **collection file is the asset**, the runner is replaceable. The Postman CLI documents a local file path for `postman collection run <collection>`,
  `-e` for an environment, `-d`/`--iteration-data` for a data file, `-i` to run only a folder or request, `--reporters cli,json,junit,html`, and no sign-in for
  a local file run. The same page says reporters other than `cli` are not supported for the newer v3 (YAML) collections and points to `postman collection migrate` for v2.1 JSON;
  it doesn't say whether a v2.1 file runs directly, so that is checked in the recording.
- **Data files and plans.** Postman's *Run collections using imported data* page says custom data files in the Collection Runner need a paid plan, and that
  uploaded data files are not supported for monitors, scheduled runs, the Postman CLI or Newman. A local file passed with `-d` to Newman is not an upload,
  and is what we use; if the lab's Postman account can't attach the file in the app, the data-driven run is shown in the terminal only.
- **Plan limits move.** Postman's resource-usage page says that "in 2026 pricing plans, collection runner runs are unlimited" and gives no Free-plan
  numbers for the CLI or monitors. Check the account's *Resource usage* page before recording.
- **`.http` files are not tests.** Microsoft Learn's page for `.http` files (Visual Studio 17.8+, VS Code REST Client) describes requests and request
  variables, and no assertions: fine for trying an endpoint, not for a suite. Learn's pointer for automated checks is integration tests with `WebApplicationFactory`
  (episode 4's xUnit tests already do that in-process; Postman tests the running container from the outside).
- **OpenAPI in the API:** `AddOpenApi()` + `MapOpenApi()` → `/openapi/{documentName}.json`; .NET 10 defaults to OpenAPI 3.1 (3.2 in .NET 11, per Learn). Learn's
  sample maps it only in Development; here `OpenApi:Enabled` (default true) decides, so the container under test serves it. Switch it off where the contract must stay private (tested).
- **Postman and OpenAPI:** Postman's February 2022 announcement covers importing and generating collections from OpenAPI 3.1 files. The *Import a specification*
  and *Generate collections* pages say an import produces folders, requests and response examples, and don't mention generated tests: the assertions in this
  episode are written by hand (the recording shows what an import actually gives you).

## References
- Blog: [API Testing with Postman — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-16-api-testing-with-postman-complete-guide-2025/)
- Microsoft Learn: [Generate OpenAPI documents (ASP.NET Core)](https://learn.microsoft.com/aspnet/core/fundamentals/openapi/aspnetcore-openapi?view=aspnetcore-10.0) (`Microsoft.AspNetCore.OpenApi`, `AddOpenApi`, `MapOpenApi`, `/openapi/v1.json`, 3.1 default, `Produces`, `ProducesValidationProblem`) ·
  [Use .http files in Visual Studio / VS Code](https://learn.microsoft.com/aspnet/core/test/http-files?view=aspnetcore-10.0) (no assertions; Endpoints Explorer) ·
  [Integration tests in ASP.NET Core](https://learn.microsoft.com/aspnet/core/test/integration-tests?view=aspnetcore-10.0) (`WebApplicationFactory`, the in-process alternative)
- Postman docs: [Newman introduction](https://learning.postman.com/docs/collections/using-newman-cli/newman-intro/) (no more updates, move to the Postman CLI) ·
  [Newman command options](https://learning.postman.com/docs/collections/using-newman-cli/newman-options/) (exit codes, `-e`, `--bail`; the rest is in the [Newman README](https://github.com/postmanlabs/newman)) ·
  [`postman collection run`](https://learning.postman.com/docs/postman-cli/postman-cli-collections/) (options, local file path, reporters) ·
  [Install the Postman CLI](https://learning.postman.com/docs/postman-cli/postman-cli-installation/) (`npm install -g postman-cli`, PowerShell and curl installers) ·
  [Test scripts](https://learning.postman.com/docs/tests-and-scripts/write-scripts/test-scripts/) and [test examples](https://learning.postman.com/docs/tests-and-scripts/write-scripts/test-examples/) (`pm.test`, Chai, status, header, response time) ·
  [`pm.response`](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-response) (`jsonSchema`, Ajv 6.12.5) ·
  [Run collections using imported data](https://learning.postman.com/docs/tests-and-scripts/running-collections/test-data/working-with-data-files) (CSV/JSON, plan note) ·
  [Import a specification](https://learning.postman.com/docs/design-apis/specifications/import-a-specification) and [Generate collections](https://learning.postman.com/docs/design-apis/specifications/generate-collections) ·
  [About resource usage](https://learning.postman.com/docs/billing/resource-usage) · [Postman supports OpenAPI 3.1](https://blog.postman.com/postman-now-supports-openapi-3-1)
- Packages: `newman@6.2.3` (npm, pinned in `package-lock.json`); `Microsoft.AspNetCore.OpenApi` 10.0.15
