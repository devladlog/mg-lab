# MG Lab #2 — Power Automate error handling: Try / Catch / Finally done right

▶️ Video: see the [series README](../../README.md)

Turn a fragile cloud flow into one that retries transient errors, catches failures, tells the team exactly what broke and still ends **Failed** in the run history.

## What's here

| File | What it is |
|---|---|
| [`script.yaml`](script.yaml) | Episode script (rendered with [`pipeline/`](../../pipeline)) |
| [`samples/try-catch-finally.definition.json`](samples/try-catch-finally.definition.json) | Reference flow definition: Try / Catch / Finally scopes, retry policy, `result()`, run URL, Terminate |
| [`expressions/cheatsheet.md`](expressions/cheatsheet.md) | Every expression and run-after setting from the episode |
| [`samples/flow-error-log.table.md`](samples/flow-error-log.table.md) | Dataverse table design for an error log |
| [`samples/report-error-child-flow.md`](samples/report-error-child-flow.md) | A reusable *Report error* child flow |

## The pattern

```
Trigger
 └─ Try (Scope)                      the real work, with tuned retry policies
 └─ Catch (Scope)    run after Try: failed, timed out
      Filter array on result('Try') → failed action + message
      Compose run URL from workflow()
      Run child flow "Report error"   (log + Teams alert)
 └─ Finally (Scope)  run after Catch: all four statuses
 └─ Terminate Failed run after Finally (all) AND Catch (succeeded, failed)
```

## Five rules

1. Try / Catch / Finally scopes.
2. Tune retry policies for transient errors.
3. `result()` + `workflow()` so every alert says what failed and links to the run.
4. Alert a team, with a business key.
5. Terminate as **Failed**. Never swallow an error.

## References

- [Employ robust error handling (Power Automate coding guidelines)](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/error-handling)
- [Use scopes to organize actions in cloud flows](https://learn.microsoft.com/power-automate/scopes)
- [Handle errors and exceptions — retry policies (Logic Apps, same engine)](https://learn.microsoft.com/azure/logic-apps/error-exception-handling)
