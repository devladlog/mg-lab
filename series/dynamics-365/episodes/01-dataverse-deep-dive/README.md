# DEVLADLOG Dynamics 365 #1 — Dataverse Deep Dive

A **Project Request** table defined as code, created through the Dataverse Web API inside a solution, then loaded
with an import you can run as many times as you like:

- table, money / date-only / choice columns, a lookup to **Account** and an **alternate key** on `mgl_requestcode`,
  all as JSON payloads that are unit-tested and reviewed like code
- **upsert by alternate key** (`PATCH .../mgl_projectrequests(mgl_requestcode='PR-0001')`), with create-only
  (`If-None-Match: *`) and update-only (`If-Match: *`) modes
- **`$batch`** import (no change set + `Prefer: odata.continue-on-error`, so one bad row doesn't stop the rest),
  and change sets when something must be atomic
- **paging** with `Prefer: odata.maxpagesize` + `@odata.nextLink`, formatted values for choice labels
- **service protection limits**: on HTTP 429 the client waits the `Retry-After` seconds and retries

The same table is used in [episode 2](../02-security-roles-teams/) to explain security roles and teams.

| Path | What it is |
|---|---|
| [`src/dvlab/schema.py`](src/dvlab/schema.py) | EntityMetadata, AttributeMetadata, OneToManyRelationshipMetadata and EntityKeyMetadata payloads — no network |
| [`src/dvlab/keys.py`](src/dvlab/keys.py) | Builds `(col='value')` key segments; doubles quotes; refuses the characters Learn says break GET/PATCH by key |
| [`src/dvlab/batch.py`](src/dvlab/batch.py) | Builds `multipart/mixed` `$batch` bodies (CRLF, ≤ 1,000 requests, no GET in a change set) and parses replies |
| [`src/dvlab/client.py`](src/dvlab/client.py) | `DataverseClient`: metadata calls with `MSCRM.SolutionUniqueName`, key status polling, upsert, paging, batch, 429 retry |
| [`src/dvlab/auth.py`](src/dvlab/auth.py) | MSAL token provider: client credentials (app user) or interactive sign-in; scope `<env>/.default` |
| [`src/dvlab/fake.py`](src/dvlab/fake.py) | **In-memory stand-in** for the slice of the Web API used here, mounted as a `requests` transport adapter (see below) |
| [`src/dvlab/cli.py`](src/dvlab/cli.py) | `python -m dvlab provision | import | report | all [--fake]` |
| [`sample/project-requests.csv`](sample/project-requests.csv) | 21 fictional rows: one duplicate code (update), one negative budget (server rejects), one code with `/` (rejected locally) |
| [`tests/`](tests/) | 41 pytest tests |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/01-dataverse-deep-dive
python3 -m pip install --user -r requirements.txt      # requests, msal, pytest
python3 -m pytest -q tests                              # 43 passed
cd src && python3 -m dvlab all --fake                   # provision + import + report against the stand-in
python3 -m dvlab all --fake --throttle-every 7          # same, with simulated HTTP 429 every 7th request
```

> **About the stand-in.** `fake.py` is not Dataverse. It imitates documented behaviour (204 + `OData-EntityId`,
> key index Pending → InProgress → Active, upsert/If-Match/If-None-Match status codes, nextLink paging,
> change-set rollback, 429 + Retry-After) so the client code path can run in CI. Its error messages start with
> `fake:` on purpose. The lab-tenant run in [demo.md](demo.md) is what proves real behaviour.

## Run against an environment (needs tenant)

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
# either an app registration + application user with System Customizer (or a custom role):
export AZURE_TENANT_ID=... AZURE_CLIENT_ID=... AZURE_CLIENT_SECRET=...
# or nothing else: an interactive browser sign-in is used
cd src
python3 -m dvlab provision --solution MGLabDataverse   # the solution must exist (publisher prefix mgl)
python3 -m dvlab import
python3 -m dvlab import                                 # second run: same 18 records, nothing duplicated
python3 -m dvlab report --page-size 5
```

## What we learned / gotchas

- **An alternate key exists before it works.** Creating it returns at once; the index is built by a background job
  and `EntityKeyIndexStatus` goes Pending → In Progress → Active (or Failed). `provision` polls
  `EntityDefinitions(LogicalName='mgl_projectrequest')/Keys` until it's Active. If it fails (existing duplicates),
  fix the data and call `ReactivateEntityKey`.
- **A date-only column needs two settings, not one.** `Format: DateOnly` only changes the display; without
  `DateTimeBehavior: {"Value": "DateOnly"}` Dataverse creates the column with the default **User local** behavior and
  stores the user's local midnight in UTC (a due date picked in Lisbon in summer is stored as 23:00 the day before).
  Learn advises against Date only format with User local behavior, and a DateOnly behavior can't be changed after
  creation. `mgl_duedate` sets both (found in episode 5; the first version of this episode set only the format). In the
  Web API the column is then an `Edm.Date`, so the import sends `YYYY-MM-DD` as is.
- **Some characters break GET/PATCH by key**: `/ < > * % & : \ ? +`. The client refuses those values before sending
  (`PR/0019` in the sample), instead of getting a confusing error back.
- **Don't send key columns in the body of an upsert.** On update they're ignored; on create the values from the URL
  are used. The client strips them.
- **Plain upsert doesn't tell you whether it created or updated** (204 either way). `Prefer: return=representation`
  gives 201 vs 200, at the cost of an extra retrieve — use a `$select` of the primary key only.
- **Change set vs. plain batch.** A change set is one transaction: one bad row rolls back the rest (tested). For
  imports, a batch without a change set plus `Prefer: odata.continue-on-error` keeps the good rows.
- **Paging:** `$skip` isn't supported; never edit `@odata.nextLink`; resend the same `odata.maxpagesize` (max
  5,000); order by something unique or rows can repeat across pages.
- **429 is normal for bulk work.** Default limits per user, per web server: 6,000 requests and 20 minutes of combined
  execution time in a 5-minute sliding window, 52+ concurrent requests. Wait `Retry-After` seconds and retry. Batching
  doesn't bypass the limits; it trades the request-count limit for the execution-time limit.
- The official **Dataverse SDK for Python** (`PowerPlatform-Dataverse-Client`) exists and does much of this for you;
  this episode uses plain `requests` so every header is visible. Its install needs pandas, which we didn't want here.

## References
- [Create and update table definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-definitions-using-web-api)
- [Create and update column definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-column-definitions-using-web-api)
- [Configure the behavior and format of the date and time column by using code](https://learn.microsoft.com/power-apps/developer/data-platform/behavior-format-date-time-attribute)
- [Create and update table relationships using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-relationships-using-web-api)
- [Work with alternate keys](https://learn.microsoft.com/power-apps/developer/data-platform/define-alternate-keys-entity) (limits, allowed column types, index status)
- [Customize tables and columns with the Python SDK — alternate keys](https://learn.microsoft.com/power-apps/developer/data-platform/sdk-python/metadata#alternate-keys) (poll before upserting; `POST .../Keys`)
- [Use Upsert to create or update a record](https://learn.microsoft.com/power-apps/developer/data-platform/use-upsert-insert-update-record)
- [Perform conditional operations using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/perform-conditional-operations-using-web-api)
- [Execute batch operations using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/execute-batch-operations-using-web-api)
- [Page results using OData](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/page-results)
- [Service protection API limits](https://learn.microsoft.com/power-apps/developer/data-platform/api-limits)
- [Use connection strings in XRM tooling](https://learn.microsoft.com/power-apps/developer/data-platform/xrm-tooling/use-connection-strings-xrm-tooling-connect) (sample AppId for development)
- [Dataverse SDK for Python — getting started](https://learn.microsoft.com/power-apps/developer/data-platform/sdk-python/get-started)
- Blog: [Dataverse Deep Dive — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-26-dataverse-deep-dive-complete-guide-2025/)
