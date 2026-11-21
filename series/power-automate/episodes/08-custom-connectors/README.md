# DEVLADLOG Power Automate #8: A GitHub issue becomes an IT request

A **custom connector built from files** (an OpenAPI 2.0 definition, an API properties file and a settings file) and the
cloud flow that uses it, plus the local material that proves the connector's webhook trigger, authentication and
policies **before anyone creates a webhook on GitHub**.

Contoso IT (the team from episodes 1 to 6) takes requests in the **IT Requests** list. Some people work in GitHub, so:

- **Connector `Contoso IT GitHub`** for `api.github.com`, **Basic** authentication (user name + fine-grained personal
  access token as the password, the way Learn's own webhook tutorial does it), and three **Set HTTP header** policies
  (`X-GitHub-Api-Version: 2022-11-28`, `Accept: application/vnd.github+json`, and a `User-Agent` only when none is sent).
  - **Trigger `WhenAnIssueIsOpened`**: `x-ms-trigger: single` on `POST /repos/{owner}/{repo}/hooks`, the payload schema in
    `x-ms-notification-content`, the callback URL in the field marked `x-ms-notification-url`, and `events` (`issues`) and
    `content_type` (`json`) as **internal** fields with defaults.
  - **Delete operation `DeleteIssueWebhook`** (internal): how the platform removes the webhook again.
  - **Action `AddIssueComment`**, and an internal **`GetAuthenticatedUser`** declared as the connector's `testConnection`.
- **Flow `GitHub issue to IT request`** (solution `GitHubIntake`): trigger on the connector, trigger condition
  `action = opened`, **Select** + **Compose** to see whether the issue has the `urgent` label, SharePoint **Create item**
  in *IT Requests* (title `[GitHub] <issue title>` cut to 255 characters, priority High or Normal, Source link), then the
  connector's **Add a comment to an issue** with the request number and link.

Episode 5 of the Power Apps series built a connector for a public API with custom code and no authentication. This one is
the other half: **authentication, a trigger that registers a webhook on the service, policies**, and the lifecycle of that
webhook.

Our first draft fell into six traps, each one now a test: no defaults in the webhook body (GitHub then uses `push` and
form encoding, and the flow stays silent), no delete operation (the webhook outlives the flow), no trigger condition (GitHub's
`ping` event ran the flow and created a request titled just "[GitHub] "), a missing `User-Agent` (403), a token without
the Webhooks permission (404 when you turn the flow on) and a failed comment followed by *Resubmit* (a second request).

| Path | What it is |
|---|---|
| [`src/connector/apiDefinition.swagger.json`](src/connector/apiDefinition.swagger.json) | OpenAPI **2.0**: the trigger, the delete operation, the comment action, `GetAuthenticatedUser`, `x-ms-capabilities.testConnection` |
| [`src/connector/apiProperties.json`](src/connector/apiProperties.json) | Basic authentication connection parameters (same shape `pac connector init --connection-template BasicAuth` generates) and the three `setheader` policies |
| [`src/connector/settings.json`](src/connector/settings.json) | Settings file for `paconn`/`pac`, ids left empty |
| [`src/solution/`](src/solution) | Unpacked solution `GitHubIntake` (`pac solution unpack` layout): 1 flow, 2 connection references (SharePoint, the custom connector), 3 environment variables (site URL, GitHub owner, repository) |
| [`src/tools/build_solution.py`](src/tools/build_solution.py) | Generates the solution folder, so the flow JSON, connection references and variables stay consistent |
| [`src/connectorkit/`](src/connectorkit) | **definition.py**: JSON-schema check (OpenAPI 2.0) plus Learn's rules (size under 1 MB, certification wording rules, `x-ms-visibility`, webhook rules, connection parameters, policy keys, `stackOwner`). **runtime.py**: builds the request for an operation (URL, path encoding, defaults, internal fields, Basic header, policies) and subscribes and unsubscribes webhooks (DELETE on the Location header) |
| [`src/githubfake/`](src/githubfake) | In-memory `api.github.com` (auth, User-Agent, hooks, ping, issues events, comments, permissions), the **modelled platform** (subscribe on turn on, callback, trigger condition, run, unsubscribe on turn off) and our three earlier drafts. `python -m githubfake` plays it |
| [`src/flowkit/`](src/flowkit) | Harness from episodes 1-7 (lint, expression evaluator, dry-run simulator) |
| [`tests/`](tests) | 71 pytest tests: definition (30), runtime (14), flow end to end (15), gotchas (10), `pac` (2) |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+, `pytest` and `jsonschema` (validates the definition against the OpenAPI 2.0 schema). `pac` is optional: the two `pac` tests are skipped without it.

```bash
cd series/power-automate/episodes/08-custom-connectors
python -m pytest                       # 71 passed in ~7 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json        # OK
python -m githubfake                   # the flow: ping ignored, two issues, two requests, two comments, webhook removed
python -m githubfake --no-defaults     # draft 1: events [push], content_type form, nothing ever arrives
python -m githubfake --no-delete       # draft 2: the webhook is still on GitHub after the flow is off
python -m githubfake --no-condition    # draft 3: the ping creates "[GitHub] ", every edit a duplicate
python -m githubfake --read-only-token # token without Issues write: request created, comment 403
python tools/build_solution.py         # rewrites solution/ (idempotent)
pac solution pack --zipfile ../out/GitHubIntake.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `71 passed in 6.89s`; flow lint `OK`; the connector files have **no validator
errors and no warnings**. `python -m githubfake` prints:

```
webhook: POST 201, events ['issues'], content_type json, Location https://api.github.com/repos/contoso/it-automation/hooks/1
delivery: ping            application/json                  -> 200
delivery: issues opened   application/json                  -> 200
delivery: issues opened   application/json                  -> 200
delivery: issues edited   application/json                  -> 200
flow runs: ['Succeeded', 'Succeeded']   callbacks ignored by the trigger condition: 2
IT request #41: "[GitHub] Laptop won't boot before a client demo" priority High
IT request #42: '[GitHub] Need a second monitor' priority Normal
comment on issue #1 by contoso-it-bot: Thanks, alex-demo. Contoso IT is tracking this as IT request #41: ...
comment on issue #2 by contoso-it-bot: Thanks, sam-demo. Contoso IT is tracking this as IT request #42: ...
-- the flow is turned off
unsubscribe: DELETE 204
webhooks left on GitHub: 0
```

## How the material was made, and what still needs the tenant

The connector files were written from Learn (webhook trigger tutorial, OpenAPI extensions, policy templates, FAQ,
certification requirements, `pac connector`) and GitHub's REST and webhook docs, and checked with the OpenAPI 2.0 JSON
schema. The flow was written from the SharePoint connector conventions used in episodes 1-6 and run with `flowkit`
against mocks for SharePoint and, for the connector's action, against `connectorkit.Runtime` + the fake GitHub, so a
wrong parameter name in the flow or a wrong header in the connector shows up as a failing test.

**The fake GitHub and the modelled platform exist only for the automated tests.** The demo (demo.md) uses the real
GitHub, the real Power Automate and the real SharePoint. **Needs tenant:** creating the connector (`pac connector create`
needs a sign-in), the connection, the flow and the real webhook on a throwaway GitHub repository.

## What we learned / gotchas

- **The trigger is three pieces in the definition, and the platform needs all of them.** Learn: the create operation with
  `x-ms-trigger: single`, `x-ms-notification-content` for the payload GitHub posts back, and a **delete operation**,
  because the platform tries to delete the webhook when you update the trigger or delete the flow. The field that gets the
  callback URL carries `x-ms-notification-url: true`. The validator refuses a webhook trigger without any of them
  (`test_the_validator_catches[no delete operation]`, `...[no notification url]`, `...[no notification content]`).
- **Unsubscribe uses the `Location` header.** Learn: the API **must** return a `Location` header with the path for the
  DELETE in the 201 response; the delete call uses the same connection and has no header of its own. Without the header
  (or the operation) nothing removes the webhook (`test_without_a_location_header_...`, `test_draft_2_...`). Learn says
  GitHub's header looks like `https://api.github.com/repos/<user>/<repo>/hooks/<id>`; GitHub's own create-webhook page
  doesn't document the header, so **demo step 6 checks that a webhook really disappears**.
- **Set the defaults GitHub doesn't.** GitHub's create-webhook defaults are `events: ["push"]` and `content_type: form`
  (GitHub docs). With form encoding "the JSON payload is sent as a form parameter called `payload`" (GitHub docs). Our
  first draft left both out: the connector worked, the webhook was created, and issues never arrived
  (`test_draft_1_...`). The fix is internal fields with defaults. Learn: for **internal** parameters that are **required**
  you must give default values; the validator checks it.
- **A ping is an event too.** GitHub docs: after you create a webhook, "GitHub will send you a simple `ping` event".
  The `issues` event also carries `edited`, `labeled` and other actions. Without a trigger condition our flow ran for the
  ping (title "[GitHub] ", then failed on the comment) and ran again for every edit (a duplicate request and a second
  comment): `test_draft_3_...` (two tests). The condition is `@equals(triggerBody()?['action'], 'opened')`.
- **GitHub wants a User-Agent.** GitHub docs: "All API requests must include a valid `User-Agent` header", requests
  without one are rejected. Policy templates are Learn's way to add a header to every request: **Set HTTP header** with
  `existsAction` `override`, `skip` or `append`, run on `Request`, for chosen operations or (no operations listed) for all
  of them. We use `skip` for the User-Agent so a header the platform already sends isn't replaced. Whether the platform
  sends one by itself is **not documented**, hence the policy (`test_without_the_user_agent_policy_github_answers_403`).
- **Basic authentication with a fine-grained token.** Learn's webhook tutorial uses a fine-grained token as the Basic
  password, with **Webhooks: Read and write** for the repository (the GitHub create-webhook page says write is needed);
  commenting needs **Issues: write**. GitHub's authentication page says the standard way is `Authorization: Bearer <token>`
  and that username + password isn't supported; it doesn't say anything about a token as Basic password. **Demo step 4
  tests the connection.** If GitHub answers 401, change the connector to API key authentication (`Authorization`
  header, value `Bearer <token>`) and record it here.
- **A token without the Webhooks permission gets a 404.** Learn (webhook tutorial): a 404 when you turn the flow on means
  the account probably lacks permission. A token without **Issues: write** fails the comment: our fake answers 403
  (GitHub lists 403 and 404 for the endpoint), and the request already exists
  (`test_a_token_without_issues_write_...`).
- **The flow isn't idempotent.** After a failed comment, *Resubmit* (or GitHub's *Redeliver*) runs the whole flow again
  and creates a second request (`test_resubmitting_...`). The fix, if it matters to you: look the issue up in the list
  by its Source link before creating. We left it out to keep the episode short.
- **Connectors made from files: some rules from Learn.** OpenAPI **2.0 only** (no OpenAPI 3), definition **under 1 MB**,
  a premium or trial licence to run a flow with a custom connector, **50** custom connectors per user (flow limits page).
  The `stackOwner` property in the API properties file blocks `paconn update` in your own environment (Learn,
  paconn limitations), so it isn't in our file (`pac connector init` generates it as an empty string: remove it).
- **Two numbers for the same limit.** The flow limits page says **500 requests per minute per connection** for a custom
  connector; the custom connector FAQ says **10,000** for Power Automate and Power Apps (and 500 for Logic Apps). We
  don't know which one applies to a given tenant; check before you design for volume.
- **Certification rules as style rules.** Learn's certification page asks for titles of at most 30 characters without the
  words API or Connector, summaries of at most 80 characters (letters, digits, parentheses), descriptions that are full
  sentences, a summary, description and visibility on every operation and no default response with an exact schema.
  A private connector doesn't need them; the validator enforces them anyway.

### What was not verified here

- That Power Automate **tests the connection** with the `testConnection` operation when a connection is created (we
  declared it as Learn documents `x-ms-capabilities`; demo step 4 shows what happens).
- The platform's webhook lifecycle as we **modelled** it (subscribe when the flow is turned on, callback, trigger
  condition, unsubscribe when it is turned off): Learn describes subscribe on create and update and delete on update or
  delete, not whether *turn off* alone also deletes it. **Demo step 8 turns the flow off and refreshes GitHub.** If the
  webhook stays, fix the model, the tests, the narration of scene `off` and this README.
- Whether a callback the trigger condition rejects (ping, edited) appears in the run history (as Skipped?) or not; the
  tests assume no run.
- How the trigger body of a **form-encoded** delivery looks inside the flow (our model: one field `payload`).
- The flow JSON conventions we can't read from Learn: the trigger `type` `OpenApiConnectionWebhook`, the connector's
  `apiId` / connection-reference connector id (we use a placeholder `shared_contoso-5fit-5fgithub-5f0000000000000801`),
  and the SharePoint parameter names (`item/Priority/Value`, `item/SourceLink`). Demo step 7 exports the solution and the
  real JSON replaces ours.
- GitHub's exact error texts (the fake's "Bad credentials", "Resource not accessible by personal access token") and
  the `Location` header on the create response (see above).

## References

- [Use a webhook as a trigger (create, notification content, delete, Location header, GitHub tutorial)](https://learn.microsoft.com/connectors/custom-connectors/create-webhook-trigger)
- [OpenAPI extensions for custom connectors (x-ms-visibility, x-ms-trigger, x-ms-notification-url, x-ms-capabilities, x-ms-url-encoding)](https://learn.microsoft.com/connectors/custom-connectors/openapi-extensions)
- [Policy templates overview](https://learn.microsoft.com/connectors/custom-connectors/policy-templates) · [Set HTTP header template (keys, override/skip/append)](https://learn.microsoft.com/connectors/custom-connectors/policy-templates/setheader/setheader)
- [Custom connector FAQ (limits, OpenAPI 2.0 only, 1 MB, authentication types, triggers)](https://learn.microsoft.com/connectors/custom-connectors/faq)
- [Limits of automated, scheduled, and instant flows (custom connector limits, premium or trial licence)](https://learn.microsoft.com/power-automate/limits-and-config#custom-connector-limits)
- [Prepare connector files for certification (title, summary and response rules, connection parameter shapes)](https://learn.microsoft.com/connectors/custom-connectors/certification-submission)
- [Create a custom connector with the CLI (paconn limitations: stackOwner)](https://learn.microsoft.com/connectors/custom-connectors/paconn-cli) · [pac connector (create, download, init, list, update)](https://learn.microsoft.com/power-platform/developer/cli/reference/connector)
- [Power Automate license types (custom connectors included in Premium)](https://learn.microsoft.com/power-platform/admin/power-automate-licensing/types#compare-power-automate-licenses)
- GitHub docs: [Create a repository webhook](https://docs.github.com/en/rest/repos/webhooks#create-a-repository-webhook) · [Creating webhooks (ping, content types)](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks) · [Create an issue comment](https://docs.github.com/en/rest/issues/comments#create-an-issue-comment) · [Authenticating to the REST API](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api) · [Getting started with the REST API (User-Agent)](https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api)
- Blog: [Custom Connectors: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-03-04-custom-connectors-complete-guide-2025/)
