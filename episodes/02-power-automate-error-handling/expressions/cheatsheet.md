# Error-handling expressions cheat sheet (MG Lab #2)

| Purpose | Expression |
|---|---|
| All actions inside the Try scope (status, inputs, outputs, error) | `result('Try')` |
| Only the failed ones (Filter array → *Where*) | `@equals(item()?['status'], 'Failed')` |
| Name of the first failed action | `first(body('Filter_failed_actions'))?['name']` |
| Error message (most connectors) | `first(body('Filter_failed_actions'))?['error']?['message']` |
| Error message (HTTP / some connectors put it in the body) | `first(body('Filter_failed_actions'))?['outputs']?['body']?['error']?['message']` |
| Safe fallback | `coalesce(<expr1>, <expr2>, 'No error message returned')` |
| Environment ID | `workflow()?['tags']?['environmentName']` |
| Flow ID | `workflow()?['tags']?['logicAppName']` |
| Flow display name | `workflow()?['tags']?['flowDisplayName']` |
| Run ID | `workflow()?['run']?['name']` |
| Link to this run | `https://make.powerautomate.com/environments/@{workflow()?['tags']?['environmentName']}/flows/@{workflow()?['tags']?['logicAppName']}/runs/@{workflow()?['run']?['name']}` |

## Run-after settings

| Block | Runs after | Statuses |
|---|---|---|
| Try | trigger | (default) |
| Catch | Try | has failed, has timed out |
| Finally | Catch | is successful, has failed, is skipped, has timed out |
| Terminate (Failed) | Finally **and** Catch | Finally: all four · Catch: is successful, has failed |

On the success path Catch is *skipped*, so Terminate is skipped and the run ends **Succeeded**.
When Try fails, Catch runs, Finally runs, then Terminate marks the run **Failed** with the real error.

## Retry policy

Most connector actions use the **Default** policy: exponential, up to 4 retries, for 408 / 429 / 5xx responses.
Override it in the action's **Settings → Retry policy** (Fixed or Exponential, count, interval, min/max interval).
Retries only help with transient errors; a wrong URL or a permissions error fails every time.
