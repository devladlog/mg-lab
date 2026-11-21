# DEVLADLOG Power Automate #1: Cloud flows fundamentals

Two real cloud flows for an **IT Requests** SharePoint list, built inside a solution and **tested locally before
they touch the tenant**:

- **IT request intake** (automated): triggers on a new list item, skips anything titled `[TEST] ...` with a
  *trigger condition*, sets a 4-hour (High) or 24-hour target, alerts on-call for High priority, marks the item
  *Triaged* and acknowledges the requester.
- **IT requests daily digest** (scheduled): weekdays 08:00 London time, gets open items, filters the overdue ones
  (comparing `ticks()`, not strings) and emails one HTML table. No email when nothing is open.

The flows are plain JSON inside an unpacked solution, so the episode also ships **flowkit**, a small Python harness
that lints the definitions and dry-runs them with mocked connectors.

> flowkit is a test harness, not the Power Automate engine. It implements the subset of the workflow definition
> language our flows use, deliberately strictly (eager evaluation, no implicit nulls). The run history in the tenant
> is the source of truth; the tests make sure you get there with the right branches.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `ITRequests` (`pac solution unpack` layout): 2 cloud flows + 2 connection references |
| [`src/solution/Workflows/ITrequestintake-…101.json`](src/solution/Workflows) | Automated flow definition (trigger condition, variable, compose, condition, SharePoint + Outlook) |
| [`src/solution/Workflows/ITrequestsdailydigest-…102.json`](src/solution/Workflows) | Scheduled flow definition (recurrence, Get items, Filter array, Create HTML table, email) |
| [`src/flowkit/expr.py`](src/flowkit/expr.py) | Expression evaluator (WDL subset: `?[ ]`, `@{ }` interpolation, comparisons, dates, `ticks`) |
| [`src/flowkit/lint.py`](src/flowkit/lint.py) | Linter: runAfter graph, variables, connection references, trigger conditions, Learn limits, "skipped last action after a handled failure" |
| [`src/flowkit/sim.py`](src/flowkit/sim.py) | Dry-run simulator: runAfter statuses, If/Switch/Scope/Foreach, Terminate, mocked connectors |
| [`src/samples/`](src/samples) | SharePoint-shaped trigger payloads (High, Normal, `[TEST]`, empty columns), Get items output, mocks |
| [`tests/`](tests) | 47 pytest tests (expressions, lint rules, both flows, `pac solution pack`) |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ and pytest. `pac` (Power Platform CLI) is optional; the pack test is skipped without it.

```bash
cd series/power-automate/episodes/01-cloud-flows-fundamentals
python -m pytest                       # 47 passed in ~2 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m flowkit run solution/Workflows/ITrequestintake-*.json \
    --trigger samples/it-request-high.json --mocks samples/mocks-intake-ok.json --now 2026-01-05T09:00:00Z
python -m flowkit run solution/Workflows/ITrequestintake-*.json \
    --trigger samples/it-request-test.json --mocks samples/mocks-intake-ok.json   # Run: Skipped

pac solution pack --zipfile ../out/ITRequests.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `47 passed in 2.01s`; `pac solution pack` → `Packed Solution.`

## How the material was made, and what still needs the tenant

The two definitions were written from the connector references (operation IDs `GetOnNewItems`, `PatchItem`,
`GetItems`, `SendEmailV2`) and the `clientdata` format documented in *Work with cloud flows using code*. The solution
was packed, then unpacked with `pac solution unpack` so the folder has the real CLI layout, and the round trip is
tested. **Import into an environment has not been done here** (no tenant from this machine). The recording session
builds the same flows in the designer inside a solution, exports, unpacks over `src/solution/` and re-runs the tests;
any difference the designer introduces (for example the list GUID instead of the list name in `table`, or extra
`metadata`) is then committed. Steps are in [`demo.md`](demo.md).

## What we learned / gotchas

- **A false trigger condition means no run at all.** "If the trigger condition isn't met, the flow isn't triggered,
  and no run history is logged." You only see a skipped trigger check under *All runs*. A Condition as the first
  action would still start (and bill) a run for every item. Every trigger condition must start with `@`.
- **`startsWith` and `endsWith` are not case-sensitive; `contains` and `replace` are.** So `[TEST]` and `[test]`
  are both filtered by one condition, but `contains(array, 'high')` won't match `High`. Both cases have a test.
- **`?[ ]` is the null ignore operator.** `triggerBody()['Priority']['Value']` fails the run when the choice column
  is empty; `triggerBody()?['Priority']?['Value']` returns null. Test `test_missing_title_and_priority…`.
- **Variables only at the top level.** Initialize variable can't sit inside a scope, condition or loop; the linter
  flags it.
- **Expressions in a trigger's inputs are evaluated when you save**, not per run (e.g. `utcNow()` becomes a fixed
  timestamp). Put time logic in actions.
- **Compare dates with `ticks()`.** `utcNow()` returns `2026-01-05T09:00:00.0000000Z` while SharePoint returns
  `2026-01-05T08:00:00Z`; comparing the strings works only by luck of the format.
- **Event triggers poll.** Create a test item and give it a few minutes before deciding the trigger is broken.
- **Limits that shape design** (Learn limits page): 30-day run duration, 500 actions and 8 nesting levels per flow,
  250 variables, Apply to each concurrency 1 by default (max 50), minimum recurrence 60 s. A flow not triggered for
  90 days might be turned off (not for premium/Process owners), and one failing continuously for 14 days is turned off.
- **flowkit is strict on purpose**: it evaluates both branches of `if()` (as the engine evaluates all arguments),
  refuses `greaterOrEquals(null, 500)`, and refuses to run a connector action without a mock.

## References

- [Overview of cloud flows (types)](https://learn.microsoft.com/power-automate/overview-cloud)
- [Customize your triggers with conditions](https://learn.microsoft.com/power-automate/customize-triggers)
- [Troubleshoot common issues with triggers](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot)
- [Troubleshoot cloud flow errors (polling)](https://learn.microsoft.com/power-automate/troubleshoot-flow-errors)
- [Limits of automated, scheduled, and instant flows](https://learn.microsoft.com/power-automate/limits-and-config)
- [Store and manage values in variables](https://learn.microsoft.com/power-automate/create-variable-store-values)
- [Expression cookbook for cloud flows (ticks, coalesce)](https://learn.microsoft.com/power-automate/expression-cookbook)
- [Functions reference for expressions (Logic Apps and Power Automate)](https://learn.microsoft.com/azure/logic-apps/expression-functions-reference)
- [Workflow Definition Language: operators (`?`)](https://learn.microsoft.com/azure/logic-apps/workflow-definition-language-schema#operators)
- [Work with cloud flows using code (clientdata, category 5)](https://learn.microsoft.com/power-automate/manage-flows-with-code)
- [Benefits of solution-aware cloud flows (connection references)](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/understand-benefits-solution-aware-flows)
- [SharePoint connector reference](https://learn.microsoft.com/connectors/sharepointonline/) · [Office 365 Outlook connector reference](https://learn.microsoft.com/connectors/office365/)
- Blog: [Cloud Flows Fundamentals: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-01-01-cloud-flows-fundamentals-complete-guide-2025/)
