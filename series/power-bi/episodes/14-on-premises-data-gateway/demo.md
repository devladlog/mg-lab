# Demo shot list — Power BI #14 On-Premises Data Gateway

## Lab environment

This episode runs on the shared Hyper-V lab (`series/LAB.md`, network 10.50.0.0/24) and in the lab tenant. **No new VM and no Azure resource**: the gateway goes on the
existing member server with a desktop, the data is the database of episode 11. Learn: gateways aren't supported on Server Core or on a domain controller, so
CON-SRV01, CON-SQL01, CON-SQL02 and CON-DC01 are out; **CON-SRV02** is the only choice.

| What | Details | Cost |
|---|---|---|
| **CON-SRV02** (gateway host) | Windows Server 2025 Datacenter Eval, Desktop Experience, 10.50.0.22, domain `lab.contoso.com`. Learn recommends 8 cores and 8 GB; the lab VM has 2 vCPU / 2-3 GB: raise its memory to 4 GB for the recording (the laptop has plenty), say honestly that it is a lab sizing. Install here: **PowerShell 7** (MSI from the PowerShell GitHub releases, needed by `Test-GatewayHost.ps1`) and **the standard mode gateway** (download link in Learn's install article). Copy this episode folder to `C:\MGLab\ep14` | free |
| **CON-SQL01** (the source) | SQL Server 2022 Developer, 10.50.0.30, TCP 1433, mixed authentication. Database **`ContosoBikesDW`** from episode 11 (its scripts `01-create-database.sql`, `02-load-data.sql`; `03` isn't needed). Then this episode's `sql/01-gateway-login.sql` | free |
| Recording laptop (Windows) | Power BI Desktop, PowerShell 7 + `MicrosoftPowerBIMgmt`, .NET 10 SDK (builds `GatewayCredential`), SSMS or `sqlcmd`, browser on the lab tenant. Reaches 10.50.0.30 and 10.50.0.22 | free |
| Lab tenant | Fabric + Power BI trial capacity, workspace `Contoso Sales (Lab)`, `labadmin` (Global Administrator, workspace Admin, registers the gateway and becomes its admin) | trial, €0 |

Screens are recorded on the laptop (Desktop, browser) and in the **Hyper-V console of CON-SRV02** (installer, gateway app, terminal).

## What was verified where

| Step | Verified in the container | Needs the lab / the tenant on the recording day |
|---|---|---|
| Module `GatewayOps` (13 functions) | 24 Pester tests with `Invoke-PowerBIRestMethod` mocked (Learn-shaped fixtures); a real TCP test on localhost | every REST call against the service |
| Credential encryption | the real Power BI SDK 4.22.0 encryptor with a 1024-bit key: `--self-test` 10 PASS; run through PowerShell by Pester | the **2048-bit path needs Windows** (CNG): run `--self-test` on the laptop. Which key size the gateway returns |
| M query | parsed by Microsoft's Power Query parser (0 errors) | running it in Desktop |
| T-SQL scripts | parsed by sqlglot (T-SQL) | running them on SQL Server 2022 |
| Numbers | Python reference from the CSVs: 4,071 lines, 1,862,401.98, five stores | the refreshed report |
| Installation, network ports test, data source, binding, refresh, certificate error | nothing | all of it |

## Setup (off camera, once)

1. **CON-SQL01**: episode 11's database exists (`SELECT COUNT_BIG(*) FROM ContosoBikesDW.dbo.FactSales` = 4,071). Run `src\sql\01-gateway-login.sql` with `-v GatewayPassword="<typed>"`, then `02-checks.sql` as the new login: CanRead 1, CanWrite 0, 4,071 lines, 1,862,401.98, 5 stores.
2. **Laptop**: `dotnet build src\GatewayCredential -m:1`, `dotnet src\GatewayCredential\bin\Debug\net10.0\gateway-credential.dll --self-test` (both key sizes must PASS on Windows), `Invoke-Pester .\tests` (24 passed).
3. **Laptop**: `Connect-PowerBIServiceAccount` as `labadmin`. Desktop: blank query with `src\queries\sales-by-store.pq` in the advanced editor, Close & apply (credentials: Database, user `pbi_gateway_reader`), a card for Sales Amount (sum), one for Order Lines (sum), a table by Store. Save as `ContosoGateway`. **Do not publish yet** (screen 1).
4. **Rehearsal of the code path** (then undo, so the UI can create it on camera): on CON-SRV02 after installing the gateway, `./src/ps/Register-LabDataSource.ps1 -GatewayName contoso-lab-gw -WhatIf`, then for real, check `Get-GatewayDataSource`, then remove the data source in the portal. Note which of Learn's two spellings the service accepts (`dataSourceName` is what the SDK sends).
5. Capture-ready window layout: Hyper-V console of CON-SRV02 at 1920x1080 with Windows Terminal (PowerShell 7) open in `C:\MGLab\ep14\src\ps`.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `before` | `screens/before.jpg` | Desktop with the query and the three visuals (Sales Amount 1,862,401.98, Order Lines 4,071), **Home > Publish** to `Contoso Sales (Lab)`. Service: model **ContosoGateway > More options > Settings > Gateway and cloud connections**: write down what it says when no gateway matches (Learn: the gateway must be in the data source list and you in its Users). Click **Refresh now**; **Refresh history** shows the failure; open **Show** for the details. Record the real wording |
| `install` | `screens/install.jpg` | CON-SRV02 console. Terminal: `./Test-GatewayHost.ps1` (all rows `True`, last line `7 endpoint(s) tested, 0 unreachable.`; blur nothing). Edge: download the standard gateway (Learn's link), run the installer: default path, accept, **Install**, email `labadmin@<domain>` (blur the domain), **Register a new gateway on this computer**, name `contoso-lab-gw`, recovery key (typed off camera, never shown), **Configure**, summary. Gateway app: **Diagnostics > Network ports test > Start new test** until *Completed (Succeeded)*; **Open last completed test results** shows the Azure Relay hosts and ports (blur nothing, but mind the region-specific host names) |
| `datasource` | `screens/datasource.jpg` | Service, **Settings > Manage connections and gateways**: cluster `contoso-lab-gw` listed, online. **New > On-premises**: cluster `contoso-lab-gw`, name `Contoso Bikes DW (lab)`, SQL Server, server `10.50.0.30`, database `ContosoBikesDW`, authentication **Basic** (`pbi_gateway_reader`, password off camera), privacy level Organizational, **Create**: *Created new connection*. Then, in the terminal on the laptop or CON-SRV02: `./Register-LabDataSource.ps1 -GatewayName contoso-lab-gw -WhatIf -Verbose` (shows the check line `GW003 Info: 10.50.0.30 / ContosoBikesDW matches a gateway data source.` and, with `-Verbose`, the request body with `credentials` as ciphertext; the `-WhatIf` run creates nothing, so the UI-created source stays the only one) |
| `bind` | `screens/bind.jpg` | Model **Settings > Gateway and cloud connections**: the SQL source with `contoso-lab-gw` selected > **Apply** (if the gateway is offered: write down how long after creating the data source). **Refresh now**; **Refresh history**: *Completed*. Terminal: `Get-DatasetGatewayInfo -WorkspaceId $ws -DatasetId $ds` → `IsBound True`, then the report: Sales Amount **1,862,401.98**, Order Lines **4,071**, five stores (Lisboa 389,707.34, Madrid 366,058.87, Online 349,212.98, Paris 385,184.07, Porto 372,238.72: `python3 src/tools/expected.py`). Optional insert: `Test-DataSourceMatch` run against the real `Get-GatewayDataSource` with a copy of the query whose database is written `contosobikesdw`: finding GW001 *differs only in letter case* |
| `cert` | `screens/cert.jpg` | **If** the refresh fails with the SQL Server certificate error (Learn: *The certificate chain was issued by an authority that is not trusted*, for self-signed certificates): capture the failed entry's details, then on CON-SRV02 (elevated) `Import-Module ..\ps\GatewayOps\GatewayOps.psd1; Set-GatewaySqlTrustedServer -Server 10.50.0.30`, show `Old`/`New` and the `.bak` file, **restart the gateway** (gateway app > Service settings > Restart, or the Windows service; write down which you used), **Refresh now** again: *Completed*. **If the refresh already worked** (the lab SQL Server may have a trusted certificate), say so, show the `SqlTrustedServers` entry as it is, and use Learn's text only. Also try Desktop on the laptop: does it connect without `PBI_SQL_TRUSTED_SERVERS`? |

## Write down (the README's "Not verified" list)

1. The exact wording in the model settings and the refresh history before the gateway exists.
2. Public key size returned by Get Gateways (modulus length) and whether the SDK encryption works on Windows for it (`--self-test`, and the real `Register-LabDataSource.ps1`).
3. Whether `Create Datasource` accepts the body the SDK writes (`dataSourceName`), and whether `gatewayStatus` is in the response of Get Gateways.
4. Whether the certificate error happens, and whether `SqlTrustedServers` (with `10.50.0.30`) and a restart fix it. Whether the setting exists in the installed file's XML as the fixture assumes (the function refuses a file without it).
5. How long after creating the data source it can be bound.
6. After a second **Publish** of the same model: is the gateway binding gone (Learn says the association isn't kept after republish)?

## Masking

Blur: the sign-in domain (installer, gateway app account, service), the recovery key (never typed on camera), SQL password, workspace and model IDs in URLs, Azure Relay host names in the test results. `pipeline/mask.js` in the browser.

## Tear-down

1. Service: remove the data source `Contoso Bikes DW (lab)`; delete the model `ContosoGateway` and its report from the workspace (or keep them for the admin episode: say which).
2. Remove the gateway: Manage connections and gateways, the cluster, remove; then uninstall *On-premises data gateway* on CON-SRV02 (Apps). **Verify in Learn's current article on removing/uninstalling before the recording** (not checked here).
3. CON-SRV02: restore `Microsoft.PowerBI.DataMovement.Pipeline.GatewayCore.dll.config` from the `.bak` if `Set-GatewaySqlTrustedServer` ran; delete `C:\MGLab\ep14`; give the VM back its memory setting.
4. CON-SQL01: `src\sql\99-teardown.sql` (drops the login and user; `ContosoBikesDW` stays for episode 11).
5. Laptop: delete `src\GatewayCredential\bin` and `obj`; `Disconnect-PowerBIServiceAccount`.
