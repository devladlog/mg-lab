# DEVLADLOG Power Automate #2: Approval workflows that always finish

A **Purchase request approval** cloud flow for a SharePoint list, built inside a solution and dry-run locally on
every path before anyone receives an email:

| Amount | Route |
|---|---|
| < 500 EUR | approved automatically by policy (no human) |
| 500 – 4,999 EUR | requester's manager (`Get manager (V2)`), first to respond |
| ≥ 5,000 EUR | manager, then **finance after the manager approves** (sequential with a gate) |
| no answer in 3 days at either stage | item marked *Escalated*, purchasing team gets a high-importance email |
| requester has no manager in Entra | approval goes to the purchasing team instead of failing |
| any other outcome | `Terminate` as **Failed** (fail loudly, never silently) |

The decision of each stage is written to one object variable (`outcome`, `by`, `comments`) and a `Switch` routes it
to *Approved / Rejected / Escalated*, writing `Decision by` and `Decision comments` back to the item.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `PurchaseApprovals` (`pac solution unpack` layout): 1 flow + 4 connection references (SharePoint, Outlook, Office 365 Users, Approvals) |
| [`src/solution/Workflows/Purchaserequestapproval-…201.json`](src/solution/Workflows) | The flow definition |
| [`src/flowkit/`](src/flowkit) | Lint + expression evaluator + dry-run simulator (from episode 1) **plus approval rules**: timeout required, timeout handler required, `Approved`/`Rejected` flagged, and the *skipped last action* rule |
| [`src/samples/`](src/samples) | Purchase requests (120, 1,800, 12,500 EUR), approval responses (approve/reject by manager and finance), manager lookup, CLI mocks |
| [`tests/`](tests) | 42 pytest tests: routing (every path), gotchas, lint, expressions, `pac solution pack` |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

```bash
cd series/power-automate/episodes/02-approval-workflows-business-process
python -m pytest                       # 42 passed in ~2.4 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m flowkit run solution/Workflows/*.json --trigger samples/purchase-large.json \
    --mocks samples/mocks-large-finance-times-out.json --now 2026-01-05T09:00:00Z
pac solution pack --zipfile ../out/PurchaseApprovals.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `42 passed in 2.41s`; the dry run ends `Mark_escalated Succeeded`,
`Notify_purchasing_team Succeeded`, `Run: Succeeded`.

## What we learned / gotchas

- **A handled timeout can still fail the run.** Our first version had `Record finance response` (runs after the
  approval *succeeded*) and `Record finance timeout` (runs after it *timed out*) as the last two steps of the finance
  condition. When finance timed out, the handler ran, but the condition was marked **Failed**, the `Switch` was
  skipped and nobody was told. That's the documented rule: *"if a branch ends with a Skipped action, that branch's
  completion status is based on that skipped action's predecessor status… If any branch ends in failure, the entire
  workflow run is marked Failed"*, and a scope is Failed when its final action fails. Fix: one `Finance result`
  Compose that runs after both on *Succeeded, Skipped*. We hit this in flowkit's dry run (the simulator implements
  that rule); `test_handled_timeout_can_still_fail_the_run_without_a_join` reproduces it and the linter warns about
  the pattern. **To confirm in the lab tenant** with a 5-minute timeout (demo.md step 6).
- **Outcomes are `Approve` and `Reject`, case-sensitive** (Approvals connector, known issues). A `Switch` case on
  `Approved` never matches; our default branch terminates as Failed so it can't go unnoticed. The linter warns on
  `Approved`/`Rejected` literals in flows that contain an approval.
- **Always set a timeout on the approval.** A run lasts at most 30 days and pending steps time out after that.
  Use *Settings → Timeout* (`limit.timeout`, ISO 8601, e.g. `P3D`) and give the *has timed out* path its own step.
  For decisions that can take longer than 30 days, use *Create an approval* in one flow and act on the response in
  another (approvals are stored in Dataverse).
- **`Get manager (V2)` returns "No manager found for the specified user"** when Entra has no manager set. Run the
  next step after *Succeeded* **and** *Failed*, and `coalesce()` to a fallback approver.
- **Approvals need Dataverse.** In a non-default environment the first approval flow run provisions the approvals
  database, and the user running it needs an admin role in the environment. The connector is standard: no premium
  licence needed.
- **Throttling:** the connector allows 50 approval *create* requests per flow per 60 seconds. Keep that in mind
  before bulk-loading requests into the list.
- **The creator of the flow is always shown in the approval** (anti-spoofing), and approval timestamps are UTC.

### What was not verified here

The definition was written from the connector references, not exported from a tenant. Two details are designer
conventions we could not confirm on Learn: the internal value `"approvalType": "Basic"` for *Approve/Reject – First
to respond*, and the `WebhookApprovalCreationInput/...` parameter sub-keys (Learn documents `approvalType` and
`WebhookApprovalCreationInput` as *dynamic* inputs). The recording session exports the solution built in the designer
and replaces `src/solution/` with it; the tests then run against the real JSON (see demo.md).

## References

- [Get started with approvals (approval types, Dataverse, licences)](https://learn.microsoft.com/power-automate/get-started-approvals)
- [Approvals connector reference (operations, outcomes, throttling, known issues)](https://learn.microsoft.com/connectors/approvals/)
- [Create and test an approval workflow (long-running approvals, cancel)](https://learn.microsoft.com/power-automate/modern-approvals)
- [Manage sequential approvals](https://learn.microsoft.com/power-automate/sequential-modern-approvals)
- [Differences between the approval actions](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/approvals/differences-between-flow-approval-actions)
- [Office 365 Users connector: Get manager (V2)](https://learn.microsoft.com/connectors/office365users/)
- [Handle workflow errors and exceptions (run after, branch and scope status)](https://learn.microsoft.com/azure/logic-apps/error-exception-handling)
- [Schema reference: change asynchronous duration (`limit.timeout`), Switch](https://learn.microsoft.com/azure/logic-apps/logic-apps-workflow-actions-triggers)
- [Cloud flow error code reference (ActionTimedOut, approvals)](https://learn.microsoft.com/power-automate/error-reference)
- [Limits of automated, scheduled, and instant flows (30-day run duration)](https://learn.microsoft.com/power-automate/limits-and-config)
- [Store and manage values in variables](https://learn.microsoft.com/power-automate/create-variable-store-values)
- Blog: [Approval Workflows & Business Process: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-01-02-approval-workflows-complete-guide-2025/)
