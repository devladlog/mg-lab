# Demo shot list — DEVLADLOG Power Apps #4, Dataverse integration

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant environment | Power Platform environment **`DEV`** with episodes 1–3. Changed here: alternate key *Asset tag key* and change tracking on Equipment (change tracking can't be turned off; harmless), three imported devices |
| Lab users | `labadmin` (the recording account) with System Customizer for `setup` (interactive OAuth, signed in off camera). The nightly-job identity is an **application user** (app registration with a client secret, custom role *Equipment Sync*), created and removed in this episode; application users are unlicensed |
| Entra | App registration for the nightly job, client secret with a short expiry; deleted (or its secret deleted) in tear-down |
| Licences / trials | **Power Apps Premium** (in the lab) for `labadmin` and any lab user who runs the app; cost 0 |
| Recording machine | The Windows lab laptop: maker portal / Power Apps Studio / the running app in the browser with `pipeline/mask.js`; .NET 8 SDK and a terminal (PowerShell or WSL bash) for `dotnet run` from `src/EquipmentSync` |

EquipmentSync was built and tested locally (`dotnet test`: 47 passed) against an in-memory fake of the Dataverse messages
it uses; `import --dry-run` runs without a connection. Everything below **needs the lab tenant** and has not been run
there: `setup` (metadata changes), `import`, `export`, the app user and its role.

Things to confirm in the lab and report back (fix code/tests/README if they differ):
- `RetrieveEntityRequest` with `EntityFilters.All` returns the Equipment keys (`EntityMetadata.Keys`).
- The key's logical name after `CreateEntityKey` is `contoso_assettagkey` (we assume the lower-cased schema name).
- `UpdateEntityRequest` + `PublishXml` turns on **Track changes** (check Tables → Equipment → Properties → Advanced).
- A new device created by upsert without a status really has an empty status before pass 2 (otherwise pass 2 is
  harmless but unnecessary: note what Dataverse does).
- The fault text when a token is refused (only if you can produce one; don't wait 7 days for it).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-3 (Equipment, Loan, both apps) | existing tables and apps | existing |
| `labadmin` with **System Customizer** (or System Administrator) | for `setup` only, interactive `AuthType=OAuth` (sign in off camera) | existing |
| Entra **app registration** with a client secret (lab tenant, off camera) | for the nightly-job identity | free |
| **Application user** for that app in DEV + custom role "Equipment Sync" | Equipment: Create, Write (user/BU is fine), **Read at Organization level** (RetrieveEntityChanges requires it); Learn: application users are unlicensed and need a custom role | free |
| .NET 8 SDK on the recording machine | `dotnet run` from `src/EquipmentSync` | free |

Secrets: put the connection string in an environment variable in a terminal **off camera**; never echo it. Delete the
client secret after recording.

## Steps
1. Off camera: `export DATAVERSE_CONNECTION_STRING="AuthType=OAuth;Url=https://<dev-org>.crm4.dynamics.com;..."` (maker
   account, see Learn "connection strings" for the OAuth parameters), then `dotnet run -- setup --enable-change-tracking`.
   Record the terminal (optional cutaway for `key-screen`). It's re-runnable: a second run prints "exists (Active)" and
   "Change tracking is already enabled."
2. Capture `key-screen` in the maker portal.
3. Switch the variable to the app user (`AuthType=ClientSecret;...`). In the phone app (episode 2), lend **CT-0043**.
4. `dotnet run -- import ../../samples/asset-register.csv` → capture `import-screen` (terminal + model-driven Equipment view).
   Run it a second time: everything "updated", only one ExecuteMultiple request; CT-0043 still On loan.
5. `dotnet run -- export ./state.json ./changes.csv` (full sync). In the model-driven app set CT-0043 back to Available;
   lend CT-0107 in the phone app. Export again → capture `export-screen` (output + `cat changes.csv`). Optional: delete
   CT-0514 in the model-driven app, export again → `CT-0514,,deleted`.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `key-screen` | `screens/alternate-key.jpg` | Tables → Equipment → Keys: "Asset tag key", column Asset tag, status **Active**; optional terminal cutaway of `setup` |
| `import-screen` | `screens/import-run.jpg` | Terminal with the import summary line (created/updated/failed 0/rejected 3); model-driven Equipment view with CT-0512 "Laptop 16, docked", CT-0513, CT-0514 Available, CT-0311 In repair, CT-0400 Retired, **CT-0043 On loan** |
| `export-screen` | `screens/export-changes.jpg` | Second export: "changes: 2 new or updated, 0 deleted (0 unknown), 1 page(s)" and the CSV with CT-0043 Available and CT-0107 On loan |

Optional terminal capture for the `tests` and `dryrun` scenes: `dotnet test` (47 passed) and the dry-run output.

## Masking
- Environment name and URL (`<dev-org>.crm4.dynamics.com`), tenant name, maker and app user names, app (client) id.
- Never show the connection string, the client secret, or the token inside `state.json`.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Delete the client secret (or the whole app registration) and the application user if they were created only for this.
2. Delete the devices the import created (CT-0512, CT-0513, CT-0514) or keep them for later episodes; set CT-0043 and
   CT-0107 back to Available.
3. The alternate key can stay. **Change tracking can't be turned off** (Learn) — that's expected; it's harmless.
4. Delete `state.json` and `changes.csv` from the recording machine.
