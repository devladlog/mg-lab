# Demo shot list: DEVLADLOG Power Automate #5, SharePoint flows that react to the right change

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant** (DEV environment, SharePoint Online). Everything below is **needs tenant**.

## Lab environment

No VMs, no Azure resources. Recorded in a browser on the recording laptop, signed in as `labadmin`, plus a second
browser profile (InPrivate) signed in as `alex.demo` and one as `jordan.demo` for the "who can see what" shots.

| What | Detail | Cost |
|---|---|---|
| Power Platform environment `DEV` (exists) | Solution, connection references, environment variables | none |
| Licences | `labadmin`, `alex.demo`, `jordan.demo` have M365 E5 (SharePoint, Outlook) and Power Apps Premium. SharePoint and Office 365 Outlook are **standard** connectors: no premium licence needed for this flow | none (trials in place) |
| SharePoint site **Purchasing** | Communication or team site; `labadmin` is a **site owner** (the flow's SharePoint connection needs rights to change permissions). If episode 2 already created it, reuse it | none |
| Mailboxes | `alex.demo` (requester) and a `purchasing-team` test mailbox or Microsoft 365 group | none |
| Recording machine | Power Platform CLI (`pac`) and Python 3 to export, unpack and re-run the tests | none |

Users and roles used (all fictional lab users from `series/LAB.md`): **Alex Demo** raises the request,
**Jordan Demo** is the approver shown in *Decision by* and a second requester for the "can't see it" shot,
**Sam Demo** is a purchasing member. `labadmin` owns the flow and the connection.

## Setup (≈ 40 min)

1. **Site permissions.** In Purchasing → *Site permissions*: `Sam Demo` in *Purchasing Members* (Edit). Make sure
   Alex Demo and Jordan Demo are **not** members of the site groups; give them *Contribute* on the **Purchase
   Requests list only** (List settings → Permissions for this list → Stop inheriting permissions → Grant
   permissions) so they can create and edit requests but have no access to the Orders library. Write down what you
   changed for tear-down.
2. **List** `Purchase Requests` (from episode 2, else create it): `Amount` (Currency, **required**), `Justification`
   (multiple lines), `Status` (Choice: Pending, Approved, Rejected, Escalated; default Pending), `DecisionBy`,
   `DecisionComments`, and the new column **`OrderFolder`** (single line of text, internal name exactly
   `OrderFolder`). List settings → **Versioning settings → Create a version each time you edit an item: Yes**.
3. **Library** `Orders`: create it with the name `Orders` (so the URL is `/sites/Purchasing/Orders`), add columns
   `RequestId` (Number) and `RequestAmount` (Currency).
4. **Solution** `Purchase Orders` (unique name `PurchaseOrders`, publisher prefix `cts`). Environment variables
   (type Text): `cts_PurchasingSiteUrl` = the lab site URL (no trailing slash), `cts_OrdersLibraryPath` =
   `/sites/Purchasing/Orders`.
5. **Flow** *New → Automation → Cloud flow → Automated* `Purchase order folder`, trigger SharePoint **When an item or
   a file is modified** (site = the environment variable, list `Purchase Requests`). Build it from
   `src/solution/Workflows/Purchaseorderfolder-…501.json`, renaming every action to the JSON names:
   - Trigger *Settings → Trigger conditions*: `@equals(triggerBody()?['Status']?['Value'], 'Approved')`.
   - **Get changes for an item or a file (properties only)**: Id = ID, Since = *Trigger Window Start Token*,
     Until = *Trigger Window End Token*.
   - Compose `PR reference`: `PR-@{formatNumber(triggerBody()?['ID'], '00000')}`.
   - Condition `Needs order folder`: expression `empty(triggerBody()?['OrderFolder'])` is equal to true. In the True
     branch: *Create new folder*, then three **Send an HTTP request to SharePoint** actions in parallel (`Ensure
     requester`, `Get read role`, `Break inheritance`), then `Grant requester read` after all three, *Create file*,
     *Update file properties*, `Get list item type`, `Link folder on request`, *Send an email (V2)*. Copy URIs,
     headers and bodies from the JSON.
   - Condition `Amount changed after approval` (after `Needs order folder`): *Update item* `Mark escalated`
     (Title and Amount from the trigger, Status Escalated, Decision comments) and *Send an email (V2)*
     `Notify purchasing` (Importance High).
   - On save, if the designer shows the infinite trigger loop warning, read it on camera (it's the episode's point)
     and keep going: the conditions are the guard.
6. **Run it.**
   - As Alex Demo: new request "Laptops for two new developers", 12,500. Wait for episode 2's approval flow (or,
     if it isn't deployed, set Status = Approved and Decision by = Jordan Demo by hand as labadmin). Wait for the
     poll (several minutes). Expect one run that creates `PR-000NN`, then **one quiet run** after the write-back, and
     no more. Note the real item ID; the scenes say PR-00041, adapt captions if the lab ID differs.
   - **Same-value check (important):** as labadmin, edit the approved request and save it **without changing
     anything**, or change only Justification. Expect: a run where `Mark escalated` is skipped. Then look at the
     second run's `Get changes` output: confirm `ColumnHasChanged/Amount` is **false** after our MERGE write-back.
     If SharePoint reports Amount as changed when a value is rewritten unchanged, *Mark escalated* would misfire:
     stop and update README + flow before publishing.
   - As Alex Demo: change Amount to 14,200. Expect: Status **Escalated**, Decision comments filled, high-importance
     email to purchasing, and no run for the flow's own write (trigger condition false: only a skipped check).
   - As Jordan Demo: open the Orders library: PR-000NN must not be visible. As Alex: it is, read-only.
7. **Export and test.**
   ```bash
   pac solution unpack --zipfile PurchaseOrders_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   Check the designer conventions listed in README "What was not verified here": the window token property names,
   `ColumnHasChanged`, the HTTP action's `parameters/...` keys, `item/Status/Value`, and whether `table` became the
   list GUID. If they differ, keep the export, update `spfake` (`site.py`, `rest.py`) and the tests to match, and note
   it in the README. Replace the real site URL with `https://contoso.sharepoint.com/sites/Purchasing` and any GUID
   with a zero GUID before committing.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `site` | `screens/site.jpg` | Purchase Requests list (Title, Amount, Status, Decision by, Order folder) with the request, the empty Orders library, and Versioning settings = Yes |
| `run` | `screens/run-folder.jpg` | Run details of the approval run: Get changes outputs (Status true, Amount false), the folder branch green with the three parallel REST calls |
| `folder-permissions` | `screens/folder-permissions.jpg` | PR-000NN folder with the summary file and its RequestId/RequestAmount; Advanced permissions: unique, Purchasing Owners Full Control, Purchasing Members Edit, Alex Demo Read; the Order folder link on the item. Optional insert: Jordan's view of Orders without the folder |
| `escalated` | `screens/escalated.jpg` | The request Escalated with Decision comments, and the high-importance email in the purchasing-team mailbox |

Code scenes (`trigger`, `permissions`, `merge`, `gotcha`, `fix`, `tests`) come from this folder; the `gotcha` and
`fix` terminal output is recorded locally with `python -m spfake --first-version --max-polls 4` and
`python -m spfake --amount-change`. After step 7, re-run them and paste the real output if it changed.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Mask the tenant name in every SharePoint URL (address bar, Order folder links, email links), the environment ID in
  make.powerautomate.com, list and item GUIDs, and principal IDs in REST outputs. Only the fictional lab users
  (Alex Demo, Jordan Demo, Sam Demo, Lab Admin) on screen.
- Run outputs of `Ensure requester` include the user's login name: collapse or mask.

## Tear-down

- Turn the flow off (it polls the list all the time).
- Delete the test requests and the PR folders in Orders (or keep them for episode 7); undo the list permissions and
  group memberships from step 1.
- Remove the exported zip from the recording machine after unpacking.
