# MG Lab #6 — File share → SharePoint migration with PnP PowerShell

A small, testable migration toolkit: inventory, pre-flight checks, idempotent provisioning, migration with metadata
and original dates, a log line per file, and verification. Demoed on a real tenant with a fictional legacy share.

| Path | What it is |
|---|---|
| [`src/MgMigration.psm1`](src/MgMigration.psm1) | The module: mapping, pre-flight (`Test-MgMigrationItem`), inventory, provisioning, migration, verification |
| [`tests/MgMigration.Tests.ps1`](tests/MgMigration.Tests.ps1) | 17 Pester tests for the pure functions (no SharePoint needed) |
| [`sample/New-LegacyShare.ps1`](sample/New-LegacyShare.ps1) | Creates a fictional legacy share (33 files, including the usual problems) |
| [`setup/register-pnp-app.sh`](setup/register-pnp-app.sh) | Creates your own Entra app for PnP (delegated permissions) and grants consent — Cloud Shell friendly |
| [`run-migration.ps1`](run-migration.ps1) | End-to-end run: inventory → connect → provision → migrate → verify (supports `-WhatIf`) |

## Run it (Azure Cloud Shell)
```bash
./setup/register-pnp-app.sh                      # prints the client id
pwsh
Install-Module PnP.PowerShell, Pester -Scope CurrentUser
Invoke-Pester ./tests
./sample/New-LegacyShare.ps1
./run-migration.ps1 -SiteUrl https://<tenant>.sharepoint.com/sites/<site> -ClientId <client-id>
```

## Design choices
- **Folders become metadata.** Legacy folders map to a `Department` choice; deep folder paths disappear (and so do
  most path-length problems). `LegacyPath` keeps the original location for traceability.
- **Original dates survive.** Metadata is written with `UpdateOverwriteVersion`, so `Modified` keeps the file-share date
  and no extra version is created.
- **Idempotent.** Re-running skips files already migrated (matched on `LegacyPath`) and upgrades columns in place.
- **Delegated auth.** The shared PnP Management Shell app was deleted on 9 September 2024; your own app with delegated
  permissions can never do more than the signed-in user.

> **Lesson from the demo:** a single line of text column holds 255 characters. One legacy path had 326, so `LegacyPath`
> is a multi-line text column. Pre-flight didn't catch it — the per-file log did.

For terabytes, use [Migration Manager](https://learn.microsoft.com/sharepointmigration/mm-get-started) or the
[SharePoint Migration Tool](https://learn.microsoft.com/sharepointmigration/introducing-the-sharepoint-migration-tool);
script the parts that need your own rules.

## References
- [SharePoint limits (400-character paths, 250 GB files)](https://learn.microsoft.com/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits)
- [Guide to migrating file shares](https://learn.microsoft.com/sharepointmigration/fileshare-to-odsp-migration-guide)
- [Register an Entra ID app for PnP PowerShell](https://pnp.github.io/powershell/articles/registerapplication.html)
- [PnP Management Shell changes](https://pnp.github.io/blog/post/changes-pnp-management-shell-registration)
