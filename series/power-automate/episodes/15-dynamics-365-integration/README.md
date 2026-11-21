# DEVLADLOG Power Automate #15: Dynamics 365 integration without the surprises

A **Dynamics 365 Sales** follow-up built the way the purchasing episodes were (same 5,000 EUR threshold, fictional
Fabrikam / Alex Demo data), plus the checks around it that can be proven without a tenant:

| Flow | Trigger | What it does |
|---|---|---|
| **Won opportunity follow-up** | Dataverse *When a row is added, modified or deleted*: table Opportunity, Update, scope Organization, *Select columns* `statecode`, *Filter rows* `statecode eq 1` | Reads the opportunity (with the account expanded), looks for an existing *Kick-off call* task, creates it if there is none (regarding the opportunity, owner = deal owner, due in 3 days) and mails finance when the deal is worth 5,000 EUR or more |
| **Overdue opportunities digest** | Recurrence, Mondays 08:00, `GMT Standard Time` | *List rows* on opportunities (`statecode eq 0 and estimatedclosedate lt <today>`, expand account, order by close date then id, top 50), one HTML table, one mail; nothing is sent when nothing is overdue |

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `SalesFollowUp` (`pac solution unpack` layout): the two flows and 2 connection references (Dataverse, Office 365 Outlook) |
| [`src/tools/build_flows.py`](src/tools) | Writes the two flow JSON files (so the shapes stay reviewable in Python) |
| [`src/d365kit/`](src/d365kit) | `odata.py` (literals, `entityset(id)` binding, filter-text checks from Learn, a small filter **evaluator**), `triggers.py` (reads the trigger settings, `fires()` = what starts a run, 6 lint rules), CLI `python -m d365kit check-filter / fires / lint / bind` |
| [`src/scripts/Invoke-DataverseQuery.ps1`](src/scripts) | PowerShell 7: runs the text of a *Filter rows / Select columns / Expand query / Sort by* box against the Web API: paging with `@odata.nextLink`, `Prefer: odata.maxpagesize`, formatted values, 429 + `Retry-After`, `-PrintOnly`. Token from `$env:DATAVERSE_TOKEN`. **Needs tenant** to run for real |
| [`src/flowkit/`](src/flowkit) | Lint + expression engine + dry-run simulator from episodes 1 to 13 (copied, unchanged) |
| [`src/samples/`](src/samples) | Opportunity rows (won, reopened, five open ones), zero-GUID ids |
| [`tests/`](tests) | 50 pytest tests (one of them runs the 12 Pester tests of the script and one runs `pac solution pack`); [`script.yaml`](script.yaml) draft script (15 scenes) · [`demo.md`](demo.md) shot list |

## Run it

```bash
cd series/power-automate/episodes/15-dynamics-365-integration
python -m pytest                      # 50 passed in ~41 s (includes pac solution pack and the Pester suite)
pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester ./tests/Invoke-DataverseQuery.Tests.ps1"   # 12 passed (Pester 6.2, PowerShell 7.6)

cd src
python -m flowkit lint solution/Workflows/Wonopportunityfollowup-*[0-9].json      # OK
python -m d365kit lint solution/Workflows/*[0-9].json                              # OK
python -m d365kit fires --flow solution/Workflows/Wonopportunityfollowup-*[0-9].json \
       --row samples/opportunity-won.json --changed statecode,statuscode           # FIRES
python -m d365kit check-filter "statecode eq 0 and estimatedclosedate lt 2026-11-21" --row samples/opportunity-open.json
pac solution pack --zipfile ../out/SalesFollowUp.zip --folder solution --packagetype Unmanaged
./scripts/Invoke-DataverseQuery.ps1 -OrgUrl https://contoso.crm4.dynamics.com -Table opportunities `
    -Filter "statecode eq 0" -Select name -PageSize 50 -PrintOnly                  # prints the request, sends nothing
```

Result on the build machine (2026-11-21): `50 passed`, Pester `Tests Passed: 12, Failed: 0`, `pac solution pack` OK.
Everything runs locally: no sign-in, no network. The PowerShell script is executed for real; only `Invoke-RestMethod`
and `Start-Sleep` are mocked. `d365kit`'s filter evaluator is **our** stand-in (eq ne gt ge lt le, and/or/not,
contains/startswith/endswith, literals, lookup paths): it proves what *we* wrote, not what Dataverse does.

## What we learned / gotchas

1. **Use the Dataverse connector.** Learn: the *Dynamics 365* connector is deprecated (shut down for new flows); new
   flows use *Microsoft Dataverse*. The connector page lists it as **Premium** for Power Automate and offers three
   connection types: OAuth, client certificate and service principal (the last two shareable).
2. **Select columns decides when it fires.** Update triggers only: the flow starts when **any** listed column is
   *included in the update request*, even with an unchanged value (`test_an_unchanged_value_in_the_request_still_fires`);
   **lookup columns aren't supported** (changes silently never trigger: `D365001`); don't list the primary key, it is in
   every update (`D365003`). Without Select columns every update can run the flow (`D365002`).
3. **Filter rows runs after the save.** The expression must be true after the change is saved, so reopening a deal
   (statecode in the request, row open again) doesn't fire (`test_reopening_does_not_pass_the_filter`).
4. **Filter text rules** (Learn, *Filter rows by using OData* and *Use lists of rows*): no `$filter=` prefix in the box;
   a quote inside a value is doubled (`'O''Bryan'`); URL-encode `& # +` and friends; no leading wildcards; at most 500
   conditions; string filters are case insensitive (`ODATA001` to `ODATA006`).
5. **Triggers repeat, so create idempotently.** A deal can be won, reopened and won again, and Learn's trigger
   troubleshooting says to design flows to be idempotent (check for the duplicate first). The flow lists tasks
   `regarding = this opportunity and subject = 'Kick-off call'` before creating one
   (`test_a_second_win_of_the_same_deal_creates_no_second_task`).
6. **Lookups in *Add a new row* are `<entity set name>(<id>)`** (Learn), and the entity set name is not always the plural:
   use *Copy set name* or `<org>/api/data/v9.2/`. The regarding column is a multi-table lookup, so its navigation
   property carries the table (`regardingobjectid_opportunity@odata.bind`); Learn warns that navigation property names
   are not always the lookup's logical name: read them from `$metadata`. Without an owner, the task belongs to the
   connection's user.
7. **List rows**: 5,000 rows by default; *Pagination* up to a threshold of 100,000 (rounded up to whole pages); with
   pagination on there is no `@odata.nextLink`; **the pagination setting does not support FetchXML** (page it in the query);
   aggregation isn't supported with FetchXML.
8. **Paging by hand**: `$top` is ignored when `odata.maxpagesize` is set and `$skip` isn't supported; use the next link
   untouched with the same page size, and order by a unique column last (`opportunityid asc`). The script refuses
   `-Top` + `-PageSize`.
9. **Service protection limits**: per user and per web server, 6,000 requests, 20 minutes of execution time and 52
   concurrent requests in a five-minute sliding window; exceeding returns **429** with `Retry-After`. Trial
   environments get a single web server (Learn). The script waits for `Retry-After` and gives up after `-MaxRetries`.
10. **Flow doesn't trigger?** Learn's checklist: background processing / administration mode, the update really
    included a Select columns column, the row passes the filter, the flow is on and the owner licensed, and the
    *callback registration* row exists.
11. **A time zone on a Recurrence needs a start time** (Learn, Recurrence): the digest has `startTime` 2026-11-23T08:00:00
    (a Monday) with `GMT Standard Time` (Learn's *Default Time Zones*: Portugal, "Dublin, Edinburgh, Lisbon, London").

### What was not verified here

- **The trigger settings of an exported flow.** `SubscribeWebhookTrigger` and the `subscriptionRequest/*` keys (`message`
  3 = Update, `scope` 4 = Organization, `entityname`, `filteringattributes`, `filterexpression`) follow episode 13's
  assumption and the designer's field names; Learn does not document them. Export the imported solution and compare
  (demo.md step 5b).
- **That *Close as Won* produces an update the Modified trigger sees.** Learn's Sales docs say closing creates an
  *Opportunity Close* activity and sets the opportunity state (`statecode` 1 = Won, `statuscode` 3 = Won); we did not
  confirm which Dataverse message the trigger receives. Fallback: trigger on *Opportunity Close* Added (demo.md 5a).
- Connector parameter names `item/regardingobjectid_opportunity@odata.bind` and `item/ownerid@odata.bind`, and the
  `$select` / `$expand` / `$top` / `$orderby` / `$filter` keys of *List rows* / *Get a row by ID*: they are the usual
  designer export names, to confirm in the export.
- `estimatedclosedate lt 2026-11-21` on a **Date Only** column, and `Prefer: odata.include-annotations=...,odata.maxpagesize=...`
  as one comma-separated header (the script's `-FormattedValues -PageSize`): both are to be run once against the real
  Web API (demo.md 5c).
- That the List rows output carries `_ownerid_value@OData.Community.Display.V1.FormattedValue` (the digest uses it).
- Whether the Dynamics 365 Sales licence includes Power Automate rights for these flows in "Sales trial": not checked;
  the plan is the self-service Power Automate Premium trial.
- `d365kit` rule `D365005` (a flow that writes back to its own trigger table) is **our heuristic**, not a Learn rule.
- `Invoke-DataverseQuery.ps1` was tested on PowerShell 7.6 only; it wasn't run on Windows PowerShell 5.1.

## References

- [Trigger flows when a row is added, modified, or deleted (Select columns, lookups, Filter rows)](https://learn.microsoft.com/power-automate/dataverse/create-update-delete-trigger)
- [Troubleshoot known issues with Dataverse (flow not triggering)](https://learn.microsoft.com/power-automate/dataverse/known-issues#flow-not-triggering)
- [Use lists of rows in flows (List rows, pagination, FetchXML)](https://learn.microsoft.com/power-automate/dataverse/list-rows)
- [Use a flow to add a row in Dataverse (lookup syntax, entity set names)](https://learn.microsoft.com/power-automate/dataverse/create)
- [Filter rows by using OData (quotes, URL encoding, wildcards, 500 conditions)](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/filter-rows)
- [Page results by using OData (maxpagesize, $top, next link, ordering)](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/page-results)
- [Service protection API limits (6,000 / 20 min / 52, 429, Retry-After)](https://learn.microsoft.com/power-apps/developer/data-platform/api-limits)
- [Web API navigation properties (single-valued, multi-table lookups)](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/web-api-navigation-properties)
- [Important changes (deprecations): Dynamics 365 connector and Dataverse (legacy)](https://learn.microsoft.com/power-platform/important-changes-coming#dynamics-365-connector-is-deprecated)
- [Microsoft Dataverse connector reference (Premium, connection types)](https://learn.microsoft.com/connectors/commondataserviceforapps/)
- [Close opportunities as won or lost (Opportunity Close activity)](https://learn.microsoft.com/dynamics365/sales/close-opportunity-won-lost-sales)
- [Opportunity Close table reference (opportunitystatecode, opportunitystatuscode)](https://learn.microsoft.com/dynamics365/developer/reference/entities/opportunityclose)
- [Troubleshoot Power Automate trigger problems (flow or actions run multiple times: idempotent design)](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot#flow-or-actions-run-multiple-times)
- [Default Time Zones (GMT Standard Time)](https://learn.microsoft.com/windows-hardware/manufacture/desktop/default-time-zones)
- Blog Complete Guide: <https://www.devladlog.com/articles/power-automate/2025-05-07-dynamics-365-integration-complete-guide-2025/>
