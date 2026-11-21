# DEVLADLOG Power Automate #10: The nightly flow that costs eleven thousand actions

One job, written two ways: a nightly flow that archives the old, finished IT requests. The draft is the way most of us
write it first; the tuned flow asks SharePoint for only the work. The material here **counts what each one costs
before it runs** and checks the flow definitions for the usual performance mistakes.

Builds on the Contoso IT scenario: the `IT Requests` list from episode 1 and the DEV environment and `cts` solution
habits from episode 9.

- **Flow `Archive done IT requests`** (solution `ITHousekeeping` 1.0.0.0, `src/solution`): recurrence at 02:00, a cutoff
  from an environment variable (`cts_ArchiveAfterDays`, 30), **Get items with an OData `$filter`** (`Status eq 'Done'
  and DoneOn lt '<cutoff>'`, indexed columns, `$top` 5000, pagination 5000), then **Apply to each with concurrency 20**
  that only calls *Update item* (`Status = Archived`), then one summary email using `length()` of the result.
- **The slow draft** (`src/drafts/slow-archive-done-requests.json`): Get items with no filter, a sequential Apply to each
  with *Get item* again, a condition and an *Increment variable*.
- **`perfkit`**: `lint` (rules P01-P10 on a flow file), `cost` and `compare` (dry run through the flowkit simulator,
  counting actions and SharePoint calls).
- **`Seed-ITRequests.ps1`**: adds (and removes) test items with PnP.PowerShell batching.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | The tuned flow as an unpacked solution (`<Managed>0</Managed>`, so pack it as Unmanaged), 4 environment variables, 2 connection references |
| [`src/drafts/slow-archive-done-requests.json`](src/drafts/slow-archive-done-requests.json) | The slow draft: a flow definition for the comparison, not part of the solution |
| [`src/tools/build_solution.py`](src/tools/build_solution.py) | Writes both, so the JSON, XML and variables stay consistent |
| [`src/perfkit/rules.py`](src/perfkit/rules.py) | Rules P01-P10 (below) |
| [`src/perfkit/budget.py`](src/perfkit/budget.py) | `measure()`: actions, SharePoint calls, throttle floor, Low profile check |
| [`src/perfkit/sharepoint.py`](src/perfkit/sharepoint.py) | **Fake** SharePoint list used by the tests and the dry run only. It models Get items, Get item and Update item, the `$filter` grammar our flows use, the 5,000 item threshold and the pagination limitation. The demo uses the real list |
| [`src/scripts/Seed-ITRequests.ps1`](src/scripts/Seed-ITRequests.ps1) | Seed and cleanup (titles start with `[TEST] seed `) |
| [`src/flowkit/`](src/flowkit) | Lint, expression evaluator and dry-run simulator, copied from episode 8 |
| [`tests/`](tests) | pytest suite and a Pester suite for the seed script |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, 3 shorts) and demo shot list |

## Run it

```bash
cd series/power-automate/episodes/10-performance-optimization
python -m pip install pytest pyyaml jsonschema       # once
python -m pytest                                      # 36 tests, about 20 s; needs no tenant, no sign-in
cd src
python -m perfkit lint drafts/slow-archive-done-requests.json solution/Workflows/*.json
python -m perfkit compare drafts/slow-archive-done-requests.json solution/Workflows/*.json
python -m perfkit cost solution/Workflows/*.json --items 2000
pwsh -NoProfile -Command "Invoke-Pester ../tests/Seed-ITRequests.Tests.ps1"
```

Result on the build machine: **36 passed** (pytest; includes the Pester suite, 5 tests, and `pac solution pack`).
Without `pac` or `pwsh` those tests are skipped.

### What the dry run says (not measured on the service)

With 40 percent of the items ready to archive. Actions = trigger plus every action run, loop iterations included.

| Items | To archive | Slow actions | Slow SharePoint calls | Tuned actions | Tuned calls |
|---|---|---|---|---|---|
| 1,000 | 400 | 2,806 | 1,401 | 406 | 401 |
| 2,000 | 800 | 5,606 | 2,801 | 806 | 801 |
| 4,000 | 1,600 | **11,206** (over 10,000) | 5,601 | 1,606 | 1,601 |

Slow = `6 + 2N + 2D`, tuned = `6 + D` (N items, D to archive); the tests assert both. The throttle floor (calls divided by
600 per minute) is a lower bound on time, not a prediction.

### Rules

| Code | Level | Finds |
|---|---|---|
| P01 | warning | Apply to each with connector calls and concurrency 1 |
| P02 | warning | Get items with no `$filter`, and an If inside the loop |
| P03 | warning | Get item re-reads the list that Get items already returned |
| P04 | error | variable action inside a loop that runs more than one item at once |
| P05 | warning | variable action in a sequential loop |
| P06 | warning | loop that only appends to an array |
| P07 | error | concurrency outside 1-50 |
| P08 | warning | Get items with no pagination and no Top Count |
| P09 | warning | pagination threshold above 5,000 (Low profile cap) |
| P10 | warning | polling trigger with no trigger condition |

Only the top-level Apply to each is checked for concurrency, because Learn says the setting takes effect only at the highest level.

## What needs the tenant

Everything in `demo.md` marked **needs tenant**: importing the solution, building the slow draft by hand, seeding the list,
real run durations, the Analytics counts, the index screen.

## What was not verified

- **Real run durations.** No number in the script comes from the service. The README table above is a dry run. Fill the real durations (slow, tuned at concurrency 1, 20, 50) in from the recording.
- **That the dry run's action counts match the service's.** They follow Learn's rule (each trigger and action is one request, loop actions once per item) and the simulator; Analytics is the check.
- **The hand-written flow JSON has never been imported by Power Automate.** `pac solution pack` accepts the folder, which only proves the layout.
- **The `$filter` datetime syntax** (`DoneOn lt '2026-10-24T02:00:00Z'`) was written from the OData pattern, not tried on a list.
- **The concurrency value of 20** is our choice. Learn gives the range 1-50 and says a high value may not be faster.
- **The pagination limitation** is modelled from Learn's text in a fake list, not reproduced on SharePoint.
- **Pagination request counts** (how many calls a 5,000 item page makes) are not modelled: Learn does not give a page size, so the call counts above are a lower bound for Get items.
- **`Seed-ITRequests.ps1`** is tested with stand-in PnP cmdlets in Pester, never against a site.
- **Standard connectors cost 0 on the lab E5 licences**; trial licences fall in the Low profile.

## Gotchas

1. **Every action is a request, and a loop multiplies them.** Learn: each trigger and action counts, a successful or failed one (not skipped), and an action in an Apply to each counts once per item. A condition and a re-read in a loop are paid for per item even when they do nothing.
2. **The Low profile is 10,000 actions per 24 hours** (transition period limits) and covers Free, Microsoft 365 plans and all licence trials. Learn calls the numbers approximations; a flow above the limit slows down, and above it for 14 days it is suspended.
3. **SharePoint allows 600 calls per minute per connection**, across all flows using it, and a different limit from the daily actions: a flow can be throttled (HTTP 429) without reaching the daily limit.
4. **Concurrency is 1 by default; 1-50 allowed, and it takes effect only on the top-level loop.** More is not always faster (Learn).
5. **Variables in a parallel loop share one value.** P04 is an error for that reason; count with `length()` or a Select after the loop.
6. **Filter on indexed columns.** Over 5,000 items an unindexed filter can fail with the list view threshold error. Learn: use `$top` and indexed column filters.
7. **Pagination off, over 5,000 items, with a filter can return nothing** if the matches are not in the first 5,000 (Learn, known limitation). The flow still succeeds.
8. **Pagination counts too.** Learn: retries and extra requests from pagination count as actions.
9. **Apply to each limits**: 5,000 items for Low, 100,000 for the other profiles; paginated items the same.
10. **Pack the source folder as Unmanaged.** `src/solution` has `<Managed>0</Managed>`; `--packagetype Managed` fails on it (episode 9's gotcha 1).

## References

- Limits of automated, scheduled, and instant flows: https://learn.microsoft.com/power-automate/limits-and-config
- Requests limits and allocations (what a request is, Analytics page shows actions): https://learn.microsoft.com/power-platform/admin/api-request-limits-allocations
- Understand platform limits and avoid throttling: https://learn.microsoft.com/power-automate/guidance/coding-guidelines/understand-limits
- Optimize flows with parallel execution and concurrency: https://learn.microsoft.com/power-automate/guidance/coding-guidelines/implement-parallel-execution
- Power Automate licensing FAQ (SharePoint 600 per minute): https://learn.microsoft.com/power-platform/admin/power-automate-licensing/faqs#action-limits-and-capacity-questions
- Get items and Get files in depth (item limits, known limitation): https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/guidance/working-with-get-items-and-get-files
- Known issues and limitations for connectors (pagination): https://learn.microsoft.com/connectors/common/known-issues#pagination-support
- Fix connection failures in cloud flows (list view threshold): https://learn.microsoft.com/power-automate/fix-connection-failures
- Optimize Power Automate triggers (trigger conditions): https://learn.microsoft.com/power-automate/guidance/coding-guidelines/optimize-power-automate-triggers
- Blog: https://www.devladlog.com/articles/power-automate/2025-07-10-performance-optimization-complete-guide-2025/
