# DEVLADLOG Power Automate #3: One expression instead of a loop

A **Weekly purchasing digest** cloud flow for the *Purchase Requests* list from episode 2, built with expressions
instead of loops and **tested locally before it touches the tenant**:

- **Every Monday 07:00 Lisbon time** (Recurrence, `GMT Standard Time`), it takes **last week, Monday to Monday, in
  Lisbon time**: `convertFromUtc` → `startOfDay` → `addDays(-7)` → `convertToUtc` for the SharePoint `$filter`.
- **Filter array** keeps the approved requests; **one Select** shapes each row: `PR-00041` reference
  (`formatNumber(ID, '00000')`), cost centre parsed from titles like `[CC-4100] Laptops` (`startsWith`, `indexOf`,
  `slice`, `toUpper`, falls back to `Unassigned`), item name, requester, amount, Lisbon submit time.
- **Total without a loop**: `xpath(xml({"root": {"row": rows}}), 'sum(/root/row/amount)')`.
- **Group by cost centre without a loop**: `sort(union(list, list))` for the distinct cost centres, then a Select
  with `count(...)` and `sum(...)` XPath queries filtered by `[costCentre="..."]`.
- **Top three**: `take(reverse(sort(rows, 'amount')), 3)`.
- Two HTML tables in one email to `finance-approvers@contoso.com`. **No email when nothing was approved.**

There is **no Apply to each** in the flow (a test asserts it).

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `PurchasingReports` (`pac solution unpack` layout): 1 flow + 2 connection references (SharePoint, Outlook) |
| [`src/solution/Workflows/Weeklypurchasingdigest-…301.json`](src/solution/Workflows) | The flow definition |
| [`src/flowkit/`](src/flowkit) | Lint + expression evaluator + dry-run simulator from episodes 1–2, **extended for this episode**: time zones and timestamp kinds ([`timefmt.py`](src/flowkit/timefmt.py)), `formatNumber`, `xml()`/`xpath()` ([`xmlfns.py`](src/flowkit/xmlfns.py)), ~45 more functions, an action-run counter, an "unknown function" and an "8,192 characters" lint rule, and `python -m flowkit eval` |
| [`src/samples/purchase-requests.json`](src/samples) | SharePoint-shaped items for a winter and a summer week (lower-case cost centre, no cost centre, Rejected/Pending rows, two items at Monday 00:30 Lisbon time) |
| [`src/samples/mocks-week-of-2026-07-06.json`](src/samples) | Mocks for the CLI dry run |
| [`src/samples/total-with-apply-to-each.json`](src/samples) · [`total-with-xpath.json`](src/samples) | The same total computed with a loop and with one expression (action count comparison) |
| [`tests/`](tests) | 81 pytest tests: Learn reference examples, the digest end to end (summer and winter), gotchas, action count, lint, `pac solution pack` |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ (uses `zoneinfo` with the system time zone database) and pytest. `pac` is optional; the pack
test is skipped without it.

```bash
cd series/power-automate/episodes/03-advanced-expressions-functions
python -m pytest                       # 81 passed in ~2.5 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m flowkit run solution/Workflows/*.json --mocks samples/mocks-week-of-2026-07-06.json --now 2026-07-13T06:00:00Z
python -m flowkit eval "formatNumber(17.35, 'C2')"                                          # $17.35
python -m flowkit eval "convertFromUtc('2026-07-13T06:00:00Z', 'GMT Standard Time', 'HH:mm')"  # 07:00
pac solution pack --zipfile ../out/PurchasingReports.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `81 passed in 2.47s`; the dry run ends `Send_digest Succeeded`,
`Run: Succeeded`; `pac solution pack` then `pac solution unpack` reproduces `src/solution/` byte for byte.

For the sample week the dry run produces: total **19,720.50 EUR**; CC-2200 1 × 4,350.50, CC-3300 1 × 120.00,
CC-4100 2 × 14,300.00, Unassigned 1 × 950.00; top three PR-00041, PR-00043, PR-00042; subject
`Approved purchases, week of 6 July 2026: 19,720.50 EUR`.

## How the material was made, and what still needs the tenant

The flow was written as JSON from the functions reference and the connector references (`GetItems`,
`SendEmailV2`), packed and unpacked with `pac`, and dry-run with flowkit. Every function the flow uses has a test
row with the **documented example** from the functions reference (`tests/test_functions.py`), so the harness
agrees with Learn wherever Learn gives a result. **Import into an environment has not been done here.** The
recording session builds the flow in the designer, runs it against the lab list, exports and unpacks over
`src/solution/`, and re-runs the tests (demo.md).

## What we learned / gotchas

- **A `Z` doesn't make a local time UTC.** `convertFromUtc` returns the converted time "without the timezone UTC
  offset". Formatting that value with a literal `Z` gives a timestamp that *looks* UTC. In January Lisbon is on
  UTC, so tests written in winter pass; in July the window starts an hour late, Monday 00:30's request disappears
  and next Monday 00:30's sneaks in (`test_a_z_suffix_doesnt_make_local_time_utc_in_summer`). Convert back with
  `convertToUtc`, and build the end of the window from local time too (DST can change inside the week).
- **Time zones are Windows ids.** Lisbon is `GMT Standard Time` ("Dublin, Edinburgh, Lisbon, London"), not
  `Europe/Lisbon`. flowkit refuses unmapped names instead of guessing.
- **There is no `sum()` function, but XPath has one.** `xml()` needs "only one root property, which can't be an
  array", and an array property becomes repeated elements (reference, `xml` example 4). `xpath(..., 'sum(...)')`
  is the reference's own example 7. XML element names can't contain spaces, so the Select uses camelCase keys and
  only the HTML table headers have spaces (`test_xml_needs_element_friendly_property_names`).
- **Every action run counts.** Power Platform requests "are counted for all types of actions … from initializing
  variables to a simple compose action". Summing 200 rows with Apply to each + Increment variable is 203 action runs
  in flowkit's count; the XPath version is 1, with the same result (`test_action_count.py`).
- **`formatNumber(17.35, 'C2')` is `$17.35`.** The locale defaults to en-US. We use a custom pattern with an explicit
  locale (`'#,##0.00', 'en-US'`) plus ` EUR`, which is stable. (flowkit only carries culture data for the locales
  the reference shows output for, en-US and is-IS, and refuses others.)
- **`substring` fails out of range, `slice` clamps.** That's documented for `substring`. Our title parser uses
  `slice`, and guards the cost centre with `if(and(startsWith(...), greater(indexOf(..., ']'), 4)), ...)`, because
  `slice(title, 1, -1)` on a title without brackets returns a wrong answer rather than an error.
- **Case:** `startsWith`, `endsWith` and `indexOf` aren't case-sensitive; `contains` is.
- **Union removes duplicates** ("no duplicates"), which with `sort()` gives a distinct, ordered list in one step.
- **Limits:** 8,192 characters per expression (lint rule), 500 actions per flow.

### What was not verified here

- The engine's behaviour with timestamps that have **no offset** when compared or converted to ticks. flowkit
  treats them as UTC; the flow never depends on it (it converts explicitly), and demo.md step 5 checks it.
- Midpoint rounding in `formatNumber` (flowkit rounds half away from zero); our data has at most two decimals.
- `sort()`, `reverse()` and `slice()` are newer functions in the reference, which states the functions apply to
  Power Automate too. demo.md step 3 confirms the designer accepts them.

## References

- [Reference guide to workflow expression functions (Logic Apps and Power Automate)](https://learn.microsoft.com/azure/logic-apps/expression-functions-reference): `convertFromUtc`, `convertToUtc`, `startOfDay`, `addDays`, `formatNumber`, `formatDateTime`, `indexOf`, `slice`, `substring`, `startsWith`, `contains`, `union`, `sort`, `reverse`, `take`, `xml`, `xpath`
- [Expression cookbook for cloud flows](https://learn.microsoft.com/power-automate/expression-cookbook)
- [Use expressions in conditions](https://learn.microsoft.com/power-automate/use-expressions-in-conditions)
- [Limits of automated, scheduled, and instant flows (characters per expression, action counting)](https://learn.microsoft.com/power-automate/limits-and-config)
- [Requests limits and allocations](https://learn.microsoft.com/power-platform/admin/api-request-limits-allocations)
- [Shape data with data operations (Compose, Select, Filter array, Create HTML table)](https://learn.microsoft.com/azure/logic-apps/logic-apps-perform-data-operations)
- [Store and manage values in variables](https://learn.microsoft.com/power-automate/create-variable-store-values)
- [Working with Get items and Get files (Top Count, filter query)](https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/guidance/working-with-get-items-and-get-files)
- [SharePoint connector reference](https://learn.microsoft.com/connectors/sharepointonline/) · [Office 365 Outlook connector reference](https://learn.microsoft.com/connectors/office365/)
- Blog: [Advanced Expressions & Functions: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-03-05-expressions-functions-complete-guide-2025/)
