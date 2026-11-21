# Demo shot list: DEVLADLOG Power Automate #2, Approval workflows

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant | Power Platform environment **`DEV`** (solution `Purchase Approvals`; the approvals database is provisioned there on first use). **SharePoint**: site `Purchasing` with list **Purchase Requests** |
| Lab users (replace the personas of the draft and the test fixtures) | `labadmin` (the recording account): maker, flow owner, admin in `DEV`. **`alex.demo` (Alex Demo)**: requester. **`sam.demo` (Sam Demo)**: Alex's manager, set as *Manager* on Alex in Entra in setup (cleared in tear-down); plays "Morgan Manager". **`jordan.demo` (Jordan Demo)**: finance approver ("Fran Finance"). **`riley.demo` (Riley Demo)**: requester **without** a manager (the fallback path) |
| Extra objects (created and deleted in this episode) | Microsoft 365 groups **`purchasing-team`** (member `taylor.demo`) and **`finance-approvers`** (member `jordan.demo`) as approval/notification recipients. Episodes 3 and 4 reuse them: delete them only after those episodes |
| Licences / trials | standard connectors only (Approvals, SharePoint, Outlook, Office 365 Users): lab E5 licences; cost 0 |
| Recording machine | The Windows lab laptop: browser (SharePoint, make.powerautomate.com, Outlook on the web for the mailboxes) with `pipeline/mask.js`; terminal with Power Platform CLI (`pac`) and Python 3 for export/unpack and the tests; separate browser profiles for Sam Demo and Jordan Demo to answer the approvals (Outlook actionable email or Teams) |

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant**. Items marked **needs tenant** can't be validated from the build container.

## Prerequisites

| What | Why | Cost |
|---|---|---|
| MG Lab DEV environment with Dataverse (exists) | Approvals are stored in Dataverse; solutions need it. If approvals were never used there, the **first run provisions the approvals database** and the person running it must have an admin role in the environment (takes a few minutes) | none |
| Standard-connector licence for the maker (Microsoft 365 or Power Automate) | Approvals, SharePoint, Outlook, Office 365 Users are standard connectors | none |
| SharePoint site `Purchasing` in the lab tenant | List the flow watches | none |
| Lab users: **Alex Demo** (requester) with manager **Sam Demo** set in Entra; **Jordan Demo** (finance); **Riley Demo** (no manager); Microsoft 365 groups `purchasing-team` and `finance-approvers` | Approvers and fallback; approvals can be assigned to users and Microsoft 365 groups | none |
| Power Platform CLI + Python 3 on the recording machine | Export/unpack and re-run tests | none |

No premium connectors, no trials, no Azure resources.

## Setup (≈ 30 min) — **needs tenant**

1. **List** `Purchase Requests`: `Amount` (Currency, EUR, **required**), `Justification` (multiple lines),
   `Status` (Choice: Pending, Approved, Rejected, Escalated; default Pending), `DecisionBy` (single line),
   `DecisionComments` (multiple lines). Internal names exactly as written.
2. **Solution** `Purchase Approvals` (unique name `PurchaseApprovals`), then *New → Automation → Cloud flow →
   Automated* `Purchase request approval`, trigger SharePoint *When an item is created*. Build it following
   `src/solution/Workflows/Purchaserequestapproval-…201.json`, renaming every action to the JSON names
   (`Manager_approval` is shown as "Manager approval", etc.):
   - Trigger condition `@equals(triggerBody()?['Status']?['Value'], 'Pending')`
   - Variables `fallbackApprover` (String) and `decision` (Object `{"outcome":"Pending","by":"","comments":""}`)
   - Condition `Is small amount` (Amount is less than 500) → *Set variable* `Auto approve`
   - No branch: *Get manager (V2)*, *Compose* `Manager email` (Settings → Run after: **is successful + has failed**),
     *Start and wait for an approval* `Manager approval` (Approve/Reject – First to respond; Settings → **Timeout P3D**),
     the two *Set variable* steps (run after **is successful** / **has timed out**), condition `Needs finance approval`
     (run after both: **is successful + is skipped**) with `Finance approval`, the two record steps and the
     **`Finance result` Compose** (run after both record steps: is successful + is skipped).
   - *Switch* `Route decision` on `variables('decision')?['outcome']`, cases `Approve`, `Reject`, `TimedOut`, default
     *Terminate* Failed.
3. **Export and test.** Export the solution (unmanaged), then:
   ```bash
   pac solution unpack --zipfile PurchaseApprovals_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   Check in particular `approvalType` and the `WebhookApprovalCreationInput/...` keys the designer wrote (README,
   "What was not verified here"). If they differ, update the tests to the exported JSON and note it in the README.
4. **Sample data** as Alex Demo: "USB-C cables" 120, "Ergonomic chairs for the support team" 1,800,
   "Laptops for two new developers" 12,500. Approve the 1,800 as Sam Demo; approve the 12,500 as Sam Demo, then as Jordan Demo.
5. **No-manager path:** one request created by Riley Demo (no manager) → the approval must go to purchasing.
6. **Timeout path (lab copy only):** save a copy of the flow (or temporarily edit) with the manager approval timeout
   set to `PT5M`. Create a request and don't answer for 5 minutes. Expect: Manager approval *timed out*, item
   **Escalated**, high-importance email to purchasing, run **Succeeded**. Then, to film the bug, delete
   `Finance result`, set the finance timeout to `PT5M`, run a 12,500 request, approve as Sam Demo and let finance time
   out: expected run **Failed** with *Route decision* skipped. **This confirms the documented branch rule in the real
   engine; if the result differs, change the `bug` scene and the README before publishing.** Restore `P3D` afterwards.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `list` | `screens/list.jpg` | Purchase Requests list with the three requests, Status and Decision by filled where decided |
| `outlook` | `screens/approval-outlook.jpg` | Actionable approval email to Sam Demo (the manager) for the 12,500 EUR request (details, link, Approve/Reject, comment box), or the same request in Teams |
| `run-sequential` | `screens/run-sequential.jpg` | Run details of the 12,500 request: Manager approval → Finance approval green, timeout steps skipped, Finance result green, Approve branch of the Switch |
| `escalated` | `screens/escalated.jpg` | Run details of the timed-out request (PT5M copy): Manager approval timed out, Record manager timeout, TimedOut branch, plus the escalation email |

Code scenes (`approval`, `fallback`, `decision`, `switch`, `bug`, `fix`, `tests`) come from this folder; after step 3,
re-run the commands and update the excerpts if the exported JSON differs.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide the tenant name in URLs, environment IDs, approval IDs and any real user name or address; only the test users
  (Alex Demo, Sam Demo, Jordan Demo, Riley Demo) on screen.
- Before committing the exported JSON, replace the real site URL with `https://contoso.sharepoint.com/sites/Purchasing`,
  real mailboxes with the `contoso.com` ones used in the tests, and any list GUID with the list name or a zero GUID.

## Tear-down

- Restore the `P3D` timeouts or delete the lab copy; turn the flow off.
- Cancel any pending approvals from *Approvals → Sent* (cancelled approvals stay in the history tab).
- Delete the sample requests if the list is kept for later episodes.
- Clear Alex Demo's *Manager* in Entra unless episode 4 is recorded next (it reuses it); delete the two Microsoft 365
  groups after episodes 3 and 4.
