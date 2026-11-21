# DEVLADLOG Power Apps #4 — Dataverse integration: upsert in, changes out

The Equipment Desk apps from episodes [1](../01-model-driven-apps/), [2](../02-canvas-apps-fundamentals/) and
[3](../03-power-fx-formulas-tips/) own the **loan** side of each device. The company's **asset register** (a separate
system, here a nightly CSV export) owns what a device *is*: name, category, serial number, purchase date, repair and
retirement. **EquipmentSync** is a small .NET 8 console app that keeps the two in step with the Dataverse SDK for .NET:

1. `setup` — an **alternate key** on `contoso_assettag` (wait for its index to be **Active**) and **change tracking** on
   the Equipment table (explicit opt-in: it can't be turned off again).
2. `import` — **upsert** every register row by asset tag with `ExecuteMultiple` (`ContinueOnError`), in small batches;
   bad rows are rejected locally with a reason; new devices get a status in a second pass.
3. `export` — **RetrieveEntityChanges** with a saved token: only what changed since the last run (devices lent in the
   app, deleted devices) goes back to the register as CSV.

| Path | What it is |
|---|---|
| [`src/EquipmentSync/Program.cs`](src/EquipmentSync/Program.cs) | The CLI (`setup`, `import [--dry-run] [--batch-size N]`, `export [--full]`) and the `ServiceClient` connection |
| [`src/EquipmentSync/TableSetup.cs`](src/EquipmentSync/TableSetup.cs) | `CreateEntityKey` + polling `EntityKeyIndexStatus`; `UpdateEntity` (ChangeTrackingEnabled) + `PublishXml` |
| [`src/EquipmentSync/AssetRegisterCsv.cs`](src/EquipmentSync/AssetRegisterCsv.cs) | CSV reader with validation (tag format, category, date, status, duplicates) |
| [`src/EquipmentSync/EquipmentImporter.cs`](src/EquipmentSync/EquipmentImporter.cs) | `UpsertRequest` per row (key in `KeyAttributes`), `ExecuteMultipleRequest` batches, status fix-up for created rows |
| [`src/EquipmentSync/ChangeExporter.cs`](src/EquipmentSync/ChangeExporter.cs) | `RetrieveEntityChangesRequest` with paging, token handling and an id-to-tag map for deletions |
| [`src/EquipmentSync/Model.cs`](src/EquipmentSync/Model.cs) | Logical names and choice values of the episode 1 table (`415000000` + index) |
| [`samples/asset-register.csv`](samples/asset-register.csv) | 12 register rows: 9 good, 3 deliberately bad |
| [`tests/EquipmentSync.Tests`](tests/EquipmentSync.Tests) | 47 xUnit tests: CSV, importer, setup, exporter, CLI end to end |
| [`tests/EquipmentSync.Tests/FakeDataverse.cs`](tests/EquipmentSync.Tests/FakeDataverse.cs) | In-memory `IOrganizationServiceAsync2` implementing just these messages, with the behaviour Learn documents |

## Run and test (no tenant needed)

```bash
cd tests
dotnet test EquipmentSync.Tests -m:1            # Passed! - Failed: 0, Passed: 47, Total: 47 (.NET 8, Dataverse.Client 1.2.27)

cd ../src/EquipmentSync
dotnet run -- import ../../samples/asset-register.csv --dry-run
# line 11 CT-51: rejected, asset tag 'CT-51' is not like CT-0042
# line 12 CT-0515: rejected, purchase date '10/11/2026' is not yyyy-MM-dd
# line 13 CT-0513: rejected, duplicate of line 9
# Upsert contoso_equipment(contoso_assettag='CT-0042') contoso_name=Laptop 14, contoso_category=415000000, ...
# 9 rows to upsert in 1 batches of up to 10, 3 rejected.        (exit code 2: there were rejected rows)
```

What the tests prove and what they don't: they prove the requests EquipmentSync builds (key in `KeyAttributes`, batch
sizes, `ContinueOnError`/`ReturnResponses`, no status for in-service devices, the second pass, paging with the cookie,
the token moving only after the last page, deletions mapped back to tags, the opt-in for change tracking) against a fake
that follows the documented behaviour. They **don't** prove the real service's responses, error codes, timings or
privileges: that's the lab run in [`demo.md`](demo.md).

## Run against an environment (needs tenant)

```bash
# setup needs a maker with System Customizer (or an app user whose role can change metadata)
export DATAVERSE_CONNECTION_STRING="AuthType=OAuth;Url=https://<dev-org>.crm4.dynamics.com;LoginPrompt=Auto;..."
dotnet run -- setup --enable-change-tracking

# the nightly job runs as an application user (unlicensed, custom role: Equipment Create/Write, Read at organization level)
export DATAVERSE_CONNECTION_STRING="AuthType=ClientSecret;Url=https://<dev-org>.crm4.dynamics.com;ClientId=<app id>;ClientSecret=<secret>"
dotnet run -- import ../../samples/asset-register.csv
dotnet run -- export ./state.json ./changes.csv
```

This has **not yet run against the lab tenant**. The SDK calls are the ones in the Learn articles below.

## What we learned / gotchas

- **Upsert can't do "only on create".** Every attribute you send is written on update too. Sending `Status = Available`
  for every register row would put each lent laptop back to Available every night. The register owns *in repair* and
  *retired*; for *in service* we send no status, and only rows the upsert **created** (`UpsertResponse.RecordCreated`)
  get `Available` in a second pass. Test: `The_nightly_import_does_not_put_a_lent_laptop_back_to_Available`.
- **Don't put the key in `Attributes`.** Learn: when the row exists, key data in `Attributes` is removed (you can't change
  a key while using it to find the row); when it doesn't, `Attributes` wins even if it differs from the key. We set the
  tag only through `new Entity(table, keyName, keyValue)`.
- **The key needs an Active index.** Learn: the index is built by a background job, `EntityKeyIndexStatus` goes Pending,
  In Progress, Active or Failed; after a failure, fix the data and use `ReactivateEntityKey`. `setup` polls and explains.
- **ExecuteMultiple, not UpsertMultiple, for a messy source.** Learn: on standard tables any error in a bulk operation
  rolls back the whole request; ExecuteMultiple runs each request in its own transaction, so with `ContinueOnError` one bad
  row costs one row. Learn also says to start with small batches (10) and let service protection limits tell you when to
  slow down; ExecuteMultiple typically allows up to 1,000 requests. `--batch-size` is configurable.
- **ServiceClient handles 429s.** Learn: `ServiceClient` "can manage any service protection API limit errors". We don't
  add our own retry loop on top.
- **Validate locally first.** Learn: alternate key values containing `/ < > * % & : \ ? +` break retrieve, update and
  upsert. The tag regex (`CT-` and four digits) rules them out, along with typos, before anything goes over the wire.
- **Change tracking is a one-way switch.** Learn: "After you enable change tracking for a table, you can't disable it."
  `setup` refuses without `--enable-change-tracking`.
- **Tokens expire.** Learn: changes are returned if the last token is within **7 days** by default
  (`Organization.ExpireChangeTrackingInDays`); older tokens throw. `export` stops with advice instead of guessing, and
  `--full` does a full resync. The token is saved only after every page is written.
- **Deleted rows come back as an id.** `RemovedOrDeletedItem.RemovedItem` is an `EntityReference`, not the row, so the
  exporter keeps an id-to-tag map from earlier runs. Learn also notes a row created and deleted between two runs still
  shows up as deleted; we count those as "unknown" instead of sending a blank tag. The first run (no token) returns every
  row as new and no deletions.
- **Permissions.** Learn: `RetrieveEntityChanges` needs organization-level Read on the table. Application users are
  unlicensed but need a custom security role (Learn: S2S authentication).
- **Read-only SDK properties in tests.** `EntityMetadata.Keys`, `EntityKeyMetadata.EntityKeyIndexStatus` and
  `EntityLogicalName` have no public setter (they're set by the server), so the fake sets them by reflection.

## References
- [Use Upsert to create or update a record](https://learn.microsoft.com/power-apps/developer/data-platform/use-upsert-insert-update-record)
- [UpsertRequest class](https://learn.microsoft.com/dotnet/api/microsoft.xrm.sdk.messages.upsertrequest)
- [Work with alternate keys (constraints, index status, ReactivateEntityKey)](https://learn.microsoft.com/power-apps/developer/data-platform/define-alternate-keys-entity)
- [RetrieveEntityKeyRequest class](https://learn.microsoft.com/dotnet/api/microsoft.xrm.sdk.messages.retrieveentitykeyrequest)
- [Execute multiple requests using the SDK for .NET](https://learn.microsoft.com/power-apps/developer/data-platform/org-service/execute-multiple-requests)
- [Use bulk operation messages (error behaviour on standard tables)](https://learn.microsoft.com/power-apps/developer/data-platform/bulk-operations)
- [Optimize performance for bulk operations](https://learn.microsoft.com/power-apps/developer/data-platform/optimize-performance-create-update)
- [Service protection API limits (retry, batch sizes)](https://learn.microsoft.com/power-apps/developer/data-platform/api-limits)
- [Use change tracking to synchronize data with external systems](https://learn.microsoft.com/power-apps/developer/data-platform/use-change-tracking-synchronize-data-external-systems)
- [RetrieveEntityChangesRequest class](https://learn.microsoft.com/dotnet/api/microsoft.xrm.sdk.messages.retrieveentitychangesrequest)
- [Use connection strings to connect to Dataverse](https://learn.microsoft.com/power-apps/developer/data-platform/xrm-tooling/use-connection-strings-xrm-tooling-connect)
- [Build web applications using server-to-server (S2S) authentication](https://learn.microsoft.com/power-apps/developer/data-platform/build-web-applications-server-server-s2s-authentication)
- [Manage application users in the Power Platform admin center](https://learn.microsoft.com/power-platform/admin/manage-application-users)
- Blog: [Dataverse Integration — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-17-dataverse-integration-complete-guide-2026/)
