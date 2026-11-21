# DEVLADLOG Power Automate #11: Your flow is fine. The policy says no.

Data policies (DLP) for cloud flows, from the maker's side and the admin's side: **predict the verdict from the flow
file before anyone saves it**, and **keep the connector classification in Git** and apply it with a script.

The scenario continues the IT Helpdesk of episodes 1-9: flows on the **IT Requests** list that end up combining
SharePoint with something the policy puts in another group.

- **`dlpkit`** reads the flow definitions (the same JSON `pac solution unpack` writes) and one or more policy files
  and says, per flow, `OK`, `SUSPENDED (mixed groups)` or `SUSPENDED (blocked connector)`. `--what-if
  CONNECTOR=GROUP` answers "what if we classified it differently?". It also lists email recipients outside your
  domains (a policy doesn't see where the data goes; see gotcha 6).
- **Policy files** (`src/policy/`): `it-dev.json` (the policy of the demo, scoped to DEV) and `baseline.json` (a
  second, tenant-wide policy that blocks MSN Weather). Same shape as `Get-DlpPolicy` plus a `scope`.
- **Four demo flows** (`src/flows/`, written by `tools/build_flows.py`): a compliant one, one with MSN Weather, one
  with the HTTP action, one that mails an external address.
- **`Apply-DlpPolicy.ps1`** moves the connectors of a real policy to the groups in the file (default group first,
  then one `Add-ConnectorsToPolicy` call per group); `-WhatIf` prints the plan. **`Export-DlpPolicy.ps1`** writes the
  real policy in the shape `dlpkit` reads.

| Path | What it is |
|---|---|
| [`src/dlpkit/model.py`](src/dlpkit/model.py) | Policy model: groups, default group, scope, unblockable connectors, validation |
| [`src/dlpkit/evaluate.py`](src/dlpkit/evaluate.py) | Connectors used by a flow, the verdict for one or several policies, `--what-if` |
| [`src/dlpkit/exfil.py`](src/dlpkit/exfil.py) | External recipients of Outlook sends (literal addresses only; expressions are listed as unchecked) |
| [`src/dlpkit/connectors.py`](src/dlpkit/connectors.py) | Names and the list of connectors Learn says can't be blocked |
| [`src/policy/`](src/policy) | `it-dev.json`, `baseline.json` |
| [`src/flows/`](src/flows) · [`src/tools/build_flows.py`](src/tools/build_flows.py) | The four demo flows and their generator (idempotent) |
| [`src/scripts/`](src/scripts) | `Apply-DlpPolicy.ps1`, `Export-DlpPolicy.ps1` (Windows PowerShell 5.1 safe) |
| [`src/flowkit/`](src/flowkit) | Lint and dry-run harness from episodes 1-9, used to check the flows are valid |
| [`tests/`](tests) | 41 pytest tests: evaluation (21), multi-policy (4), exfil and CLI (10), PowerShell (3, one of which runs the 11 Pester tests) |
| [`script.yaml`](script.yaml) | Draft video script (14 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ with `pytest` and `pyyaml`. `pwsh` with Pester 5+ is optional (those tests are skipped without it).

```bash
cd series/power-automate/episodes/11-security-data-loss-prevention
python -m pytest                      # 41 passed in ~52 s (11 Pester tests run inside one of them)

cd src
python -m dlpkit check flows --policy policy/it-dev.json --environment dev
python -m dlpkit check flows --policy policy/it-dev.json policy/baseline.json --environment dev
python -m dlpkit check flows --policy policy/it-dev.json --environment dev --what-if http=Business
python -m dlpkit check flows --policy policy/it-dev.json --environment dev --allowed-domain contoso.example
python -m dlpkit show policy/it-dev.json
python -m dlpkit groups policy/it-dev.json policy/baseline.json
python tools/build_flows.py           # rewrites flows/ (idempotent)
```

`dlpkit check` exits 1 when a flow would be suspended (so it can gate a pipeline), 2 when a policy can't be read.
With `policy/it-dev.json`, two of the four flows are suspended:

```
SUSPENDED  request-asset-lookup.json    mixed: HTTP (Non-business) | SharePoint (Business)
SUSPENDED  request-weather-note.json    mixed: MSN Weather (Non-business) | Outlook ... SharePoint (Business)
OK         acknowledge-it-request.json
```

With the baseline policy added, the weather flow's verdict changes to `blocked: MSN Weather is blocked by 'MG Lab
baseline'`: a block in any policy wins. `--what-if http=Business` makes the HTTP flow `OK` (and tells you what that
classification costs: see the demo).

## How the material was made, and what still needs the tenant

The rules in `dlpkit` were written from Learn (links below), including the example of three policies A, B and C that
Learn uses for "combined effect of multiple data policies" (`tests/test_multipolicy.py`). The flows follow the JSON
layout of episodes 1-9. The PowerShell scripts run in the tests against **stand-in cmdlets** (the real module is
Windows PowerShell 5.1 only, Learn, so it can't run under `pwsh` 7); the stand-ins exist only for Pester. **The demo
uses the real module, the real admin center and a real policy.**

**Needs tenant:** creating the policy, saving a flow into it and seeing it suspended, running the two scripts against
the real policy, exporting the real policy and the real solution to compare with `dlpkit`, and every `screen`
scene. See [`demo.md`](demo.md). No premium licence is needed for the screens (standard connectors only).

## What we learned / gotchas

1. **Three groups, one rule that matters.** Learn: a flow can't use connectors from more than one of Business and
   Non-business; Blocked connectors can't be used at all. A connector that no list names sits in the **default
   group** (policy-level setting; ours is Non-business), so "SharePoint Business, everything else default" suspends
   any flow that mixes SharePoint with a connector you never classified (`test_unlisted_connector_is_in_default_group`).
2. **Some connectors can't be blocked.** Learn lists them (Approvals, Dataverse, Microsoft 365 Outlook, SharePoint,
   Teams and others). If your default group is Blocked, they go to Non-business, and a file that lists one under
   Blocked is invalid (`validate`, same as the admin center refusing to save).
3. **Several policies: a block wins, otherwise the groups multiply.** With policies A, B and C Learn derives up to
   eight combined groups; a flow can't mix connectors from different combined groups. Policies apply by scope:
   all environments, selected ones, or all except some (`scope` in our files).
4. **Saved is not the same as allowed.** Learn: when a maker saves a flow that violates the policy, "the flow itself
   will be saved, but it will be marked as Suspended" and won't run until the violation is fixed (flows without child
   flows are evaluated synchronously). A policy created or changed **after** the flow exists is enforced by a
   background job: Learn says "in most cases, it's within an hour" and 24 hours in the most extreme cases; flows with
   child flows are evaluated asynchronously, within 24 hours. Active cloud flows suspended in the previous 7 days are
   re-activated automatically once they no longer violate any policy; the demo checks that on the real tenant.
   Through the API the suspended flow has `State=Suspended` and `FlowSuspensionReason=CompanyDlpViolation`.
5. **The policy is per environment, so it reaches every flow there.** The demo policy scoped to DEV would also
   suspend any flow in DEV that mixes SharePoint with HTTP (episodes 4 and 8). `demo.md` says what to record, how to
   remove the policy the same day and what to check afterwards.
6. **A data policy is connector-aware, not data-aware.** Learn: policies "don't control connections made using the
   connector". Nothing stops `request-external-copy.json` from mailing a SharePoint item to `reports@fabrikam.example`: both
   connectors are Business. `dlpkit check --allowed-domain` only reads literal recipients (expressions are listed as
   *not checked*), and it is a review aid, not a control. Learn's real control for destinations is endpoint filtering
   (preview) and connector action control, which `dlpkit` does **not** model.
7. **HTTP is the one that bites.** The built-in HTTP action is a connector in policy terms. Learn's endpoint-filtering
   example uses the id `http`, so `dlpkit` maps the HTTP action to it. HTTP Webhook and *When an HTTP request is
   received* have ids we couldn't confirm on Learn, so `dlpkit` reports them as **not evaluated** instead of guessing.
8. **Admin module quirks.** `Microsoft.PowerApps.Administration.PowerShell` runs on Windows PowerShell 5.1 only (Learn).
   `Get-DlpPolicy` doesn't return connectors that were never moved from the default group, so `Apply-DlpPolicy.ps1`
   treats "not listed" as "in the default group", sets the default group first and re-reads the policy before moving
   the rest. Learn's cmdlet reference confirms the `Add-ConnectorsToPolicy -Classification` values and
   `Set-DlpPolicy -DefaultGroup`.
9. **`pac admin dlp-policy list|show`** exist and are read-only (Learn). We use the PowerShell module for writing and
   treat the `pac` output as the cross-check in the demo.
10. **The scripts' PS 5.1 rules are tested**: no `??`, `?.`, ternary, `&&` or `||` (`tests/test_powershell.py`), because a
    script that only parses on PowerShell 7 is useless with this module.

### What was not verified here

- The **connector ids** of HTTP Webhook and the *Request* trigger, and the exact id string the service returns for
  the HTTP action in `Get-DlpPolicy` (we assume `http`, as in Learn's endpoint-filtering example). Demo "after
  recording" step 3 checks it.
- The **exact flow checker message** when a save is blocked, and whether the flow is shown as Suspended at once.
- That `Get-DlpPolicy` output has exactly the shape `dlpkit` assumes (`connectorGroups[].classification` as
  `Confidential`/`General`/`Blocked`, `connectors[].id`). The shape is taken from Learn's examples and the cmdlet
  reference; `Export-DlpPolicy.ps1` writes it, and the demo compares it with the real export.
- That `New-DlpPolicy` / environment-type values (we don't create policies from a script; the demo creates it in the
  admin center).
- That our verdicts equal the service's for **child flows** and for **connector action control / endpoint filtering**
  (not modelled).
- That the two scripts run clean against the real admin module (tested with stand-ins only).

## References

- [Data policies overview (process for policy changes, latency: usually within an hour, at most 24 hours)](https://learn.microsoft.com/power-platform/admin/wp-data-loss-prevention)
- [Manage data policies (create a policy, assign connectors, define scope)](https://learn.microsoft.com/power-platform/admin/create-dlp-policy)
- [Connector classification (Business, Non-business, Blocked; connectors you can't block)](https://learn.microsoft.com/power-platform/admin/dlp-connector-classification)
- [Combined effect of multiple data policies](https://learn.microsoft.com/power-platform/admin/dlp-combined-effect-multiple-policies)
- [Implement a data policy strategy (quick facts: connector aware, not connection aware; Microsoft-owned standard connectors can't be blocked)](https://learn.microsoft.com/power-platform/guidance/adoption/dlp-strategy)
- [Impact of data policies on apps and flows (design-time save marks the flow Suspended; background process)](https://learn.microsoft.com/power-platform/admin/dlp-impact-policies-apps-flows)
- [DLP policy creation for Power Automate (synchronous vs 24-hour enforcement, 7-day reactivation, `FlowSuspensionReason`, child flows)](https://learn.microsoft.com/power-automate/prevent-data-loss)
- [Data policies for the HTTP connector and endpoint filtering](https://learn.microsoft.com/power-platform/admin/dlp-custom-connector-parity)
- [Microsoft.PowerApps.Administration.PowerShell (Get-DlpPolicy, Add-ConnectorsToPolicy, Set-DlpPolicy)](https://learn.microsoft.com/powershell/powerapps/overview)
- [pac admin dlp-policy](https://learn.microsoft.com/power-platform/developer/cli/reference/admin)
- Blog: [Security and DLP: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-08-11-security-dlp-complete-guide-2025/)
