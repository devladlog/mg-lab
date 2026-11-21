# DEVLADLOG Power Automate #5: SharePoint flows that react to the right change

A **Purchase order folder** cloud flow for the *Purchase Requests* list from episodes 2 and 3, and the local
material that proves it **reacts to the right change, locks the folder down and never triggers itself forever**,
before it touches the tenant.

When episode 2's approval flow marks a request **Approved**, purchasing needs a place for the quote, the order and
the invoice. This flow:

- triggers on **When an item or a file is modified** (`GetOnChangedItems`), with a trigger condition
  `Status = Approved`, so pending and rejected edits never start a run;
- calls **Get changes for an item or a file (properties only)** (`GetItemChanges`) between the trigger's
  *Trigger Window Start* and *End* tokens, to know **which columns changed in this window**;
- if the request has no folder yet (`empty(OrderFolder)`), creates `Orders/PR-00041` (**Create new folder**),
  and uses **Send an HTTP request to SharePoint** for what the connector has no action for: `ensureuser` for the
  requester, the *Read* role definition, `breakroleinheritance(copyRoleAssignments=true,clearSubscopes=true)` on the
  folder and `addroleassignment` for the requester. Purchasing keeps its access; the requester can read only their
  own folder;
- writes a summary file (**Create file**), tags it with the request ID and amount (**Update file properties**),
  then writes the folder link back to the request with a **REST MERGE that sends only `OrderFolder`**, and emails the
  requester;
- if the **amount changed after approval** (Get changes: `Amount` changed, `Status` didn't), sets the request to
  **Escalated** and emails purchasing (high importance).

The write-back is a modification, so it triggers the flow once more: that run finds the folder and no amount change
and does nothing. Then it's quiet. Our first draft didn't check `OrderFolder` and triggered itself on every poll.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Unpacked solution `PurchaseOrders` (`pac solution unpack` layout): 1 flow, 2 connection references (SharePoint, Outlook), 2 environment variables (site URL, Orders library path) |
| [`src/solution/Workflows/Purchaseorderfolder-…501.json`](src/solution/Workflows) | The flow definition |
| [`src/spfake/`](src/spfake) | In-memory SharePoint site for the tests: lists with **versions and a change log**, the modified-items trigger with window tokens, Get changes, required columns on Update item, an **Orders library with folders, files and permissions**, and the six REST endpoints the flow calls (anything else answers 404). `python -m spfake` plays the scenario poll by poll |
| [`src/flowkit/`](src/flowkit) | Harness from episodes 1–4 (lint, expression evaluator, dry-run simulator), **extended with SharePoint lint rules**: window tokens need the modified trigger, Get changes `since` should be the start token, REST calls without `odata=nometadata`, MERGE without `__metadata.type`, and a **self-triggering loop** rule (the flow writes columns of its trigger list that no trigger condition or enclosing condition checks) |
| [`tests/`](tests) | 24 pytest tests: happy path and permissions, change detection, gotchas, lint, `pac solution pack` |
| [`script.yaml`](script.yaml) | Draft video script (15 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ and pytest (no other packages). `pac` is optional; the pack test is skipped without it.

```bash
cd series/power-automate/episodes/05-sharepoint-integration
python -m pytest                       # 24 passed in ~2.5 s (pac 2.16.1 present)

cd src
python -m flowkit lint solution/Workflows/*.json
python -m spfake                       # approve -> folder run, one quiet run, then no changes
python -m spfake --amount-change       # ... then Alex changes the amount -> Escalated, then the trigger condition stops it
python -m spfake --first-version       # the draft without the OrderFolder check: a run on every poll
pac solution pack --zipfile ../out/PurchaseOrders.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `24 passed in 2.32s`; lint `OK`; `pac solution pack` then
`pac solution unpack` reproduces `src/solution/` byte for byte. `python -m spfake --amount-change` prints:

```
Alex Demo's request #41 approved by Jordan Demo (episode 2's flow)
poll 1: run Succeeded folder, permissions, summary file, link on item, email requester  (14 actions)
poll 2: run Succeeded nothing to do  (4 actions)
poll 3: no changes
Alex Demo changes the amount to 14,200
poll 4: run Succeeded Escalated, email purchasing  (6 actions)
poll 5: item changed, trigger condition false: no run
runs: 3  folders: 1  emails: 2  status: Escalated
```

## How the material was made, and what still needs the tenant

The definition was written from the SharePoint connector reference (operation IDs `GetOnChangedItems`,
`GetItemChanges`, `CreateNewFolder`, `HttpRequest`, `CreateFile`, `PatchFileItem`, `PatchItem`; `ItemId` from
*Create file*'s `SPBlobMetadataResponse`) and the SharePoint REST articles on Learn, packed and unpacked with `pac`,
and run against `spfake`. The SharePoint and Outlook actions are mocked by `spfake`, which is strict where Learn is
explicit (see the docstring of [`site.py`](src/spfake/site.py)). **Needs tenant:** the lists, the library, a real run
with real permissions, and the export (demo.md).

## What we learned / gotchas

- **A flow that edits its own trigger list can trigger itself forever.** Learn (*Avoid anti-patterns*): "if a flow
  is triggered when a record is updated … and the flow updates the same record, it can potentially trigger itself
  forever", and the fix is trigger conditions or a check that stops the run. Our first draft created the folder and
  wrote `OrderFolder` on every approved item: every poll, a new run and a new email
  (`test_first_version_triggers_itself_forever`). The `empty(OrderFolder)` check stops it after one quiet run; the
  linter now flags writes to the trigger list that nothing checks.
- **Trigger conditions don't just save runs, they stop loops.** "While you can filter other events by adding
  conditions to the flow, the flow still runs and the calls are counted as an API request." Escalating sets
  `Status = Escalated`; the trigger condition `Status = Approved` means the flow's own write never starts a run.
- **Get changes needs versioning and the modified trigger.** "The list must have Versioning turned on", and the
  Trigger Window Start/End tokens "are only available when you use *when an item or file is modified* trigger".
  *When an item or a file is modified* doesn't fire on creation. Without versioning the action fails
  (`test_get_changes_needs_versioning`; the error text is the fake's own).
- **Changes inside one polling window are merged.** SharePoint triggers poll, and Learn warns that "the flow may
  gather more than one change in subsequent flow runs". If the amount is edited between the approval and the next
  poll, Get changes reports `Amount` *and* `Status`, and the flow can't tell the order: it treats the request as
  approved with the new amount (`test_changes_inside_one_polling_window_are_merged`). If that matters, make
  approval lock the amount (or compare against the approved amount stored at decision time).
- **Update item wants every required column.** Learn: "you always need to specify a value for all the mandatory
  fields". `Amount` is required in this list, so *Mark escalated* sends `Title` and `Amount` back unchanged
  (`test_update_item_needs_every_required_column`). For the folder link we use a **REST MERGE**, which "keeps their
  current property" for everything not sent, so the only column that changes is `OrderFolder`.
- **A list-item MERGE needs the entity type.** The `ListItemEntityTypeFullName` "must be passed as the type property
  in the metadata". We read it with `GET _api/web/lists/GetByTitle('Purchase Requests')?$select=ListItemEntityTypeFullName`
  instead of guessing it from the list name.
- **Use `Accept: application/json;odata=nometadata`.** Learn's guidance for *Send an HTTP request to SharePoint*.
  Without it, `body('Ensure_requester')?['Id']` doesn't find the ID in our fake's verbose response
  (`{"d": {...}}`) and the role assignment fails (`test_without_nometadata_the_id_is_wrapped_and_the_grant_fails`).
- **Order matters for permissions.** `addroleassignment` runs only after `breakroleinheritance` succeeded, and the
  link is written only after the grant: a wrong library path fails the run and leaves `OrderFolder` empty, so no
  one is sent to an unprotected folder and the next change retries
  (`test_a_wrong_library_path_fails_the_run_instead_of_leaving_an_open_folder`).
- **Connector facts that shape the design:** SharePoint is a standard connector; 600 API calls per connection per
  60 seconds; flows for lists only on generic lists and libraries; *Create file* "Folder Path must start with an
  existing library"; the HTTP action "may execute any SharePoint REST API you have access to", with the permissions
  of the connection's account (here, a site owner is needed to change permissions).

### What was not verified here

- **Designer conventions** not documented on Learn: the property names `{TriggerWindowStartToken}` /
  `{TriggerWindowEndToken}` in the trigger body, the shape of Get changes' output (`ColumnHasChanged/<column>`),
  the `parameters/method`, `parameters/uri`, `parameters/headers`, `parameters/body` keys of the HTTP action and
  `item/Status/Value` for a choice column. demo.md step 7 exports the real JSON and replaces ours.
- **REST shapes derived, not copied:** the two-argument `breakroleinheritance(copyRoleAssignments=…,clearSubscopes=…)`
  follows the CSOM signature `BreakRoleInheritance(bool, bool)` and Learn's parameter syntax (name=value pairs);
  `POST _api/web/ensureuser` with `{"logonName": …}` follows `Web.EnsureUser(logonName)`. Learn's REST examples show
  `breakroleinheritance(true)` and `roledefinitions/getbyname('Contribute')`.
- What *Create new folder* does when the folder already exists, whether rewriting a column with the **same value**
  makes Get changes report it as changed, and the exact error texts: `spfake` makes an assumption and says so.
  demo.md step 6 checks the same-value case, because it decides whether *Mark escalated* could misfire.

## References

- [SharePoint connector reference (operations, throttling, known issues)](https://learn.microsoft.com/connectors/sharepointonline/)
- [Microsoft SharePoint connector in Power Automate (triggers, Get changes, known limitations)](https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/sharepoint-connector-actions-triggers)
- [Working with the SharePoint Send HTTP Request flow action](https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/guidance/working-with-send-sp-http-request)
- [Avoid anti-patterns: infinite loops](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/avoid-anti-patterns)
- [Customize your triggers with conditions](https://learn.microsoft.com/power-automate/customize-triggers)
- [Set custom permissions by using the REST interface (breakroleinheritance, roledefinitions, addroleassignment)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins/set-custom-permissions-on-a-list-by-using-the-rest-interface)
- [Working with folders and files with REST (GetFolderByServerRelativeUrl, ListItemAllFields)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest)
- [Working with lists and list items with REST (ListItemEntityTypeFullName, MERGE)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins/working-with-lists-and-list-items-with-rest)
- [Complete basic operations using SharePoint REST endpoints (MERGE vs PUT, Accept header)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins/complete-basic-operations-using-sharepoint-rest-endpoints)
- [Determine SharePoint REST service endpoint URIs (parameter syntax)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins/determine-sharepoint-rest-service-endpoint-uris)
- [SecurableObject.BreakRoleInheritance(Boolean, Boolean)](https://learn.microsoft.com/dotnet/api/microsoft.sharepoint.client.securableobject.breakroleinheritance?view=sharepoint-csom) · [Web.EnsureUser(String)](https://learn.microsoft.com/dotnet/api/microsoft.sharepoint.client.web.ensureuser?view=sharepoint-csom)
- [From SharePoint Add-in workflows to Power Automate (Update item needs the mandatory fields)](https://learn.microsoft.com/sharepoint/dev/sp-add-ins-modernize/from-workflow-apps-to-power-automate)
- [Use environment variables in solution cloud flows](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/use-environment-variables)
- Blog: [SharePoint Integration: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-05-06-sharepoint-integration-complete-guide-2025/)
