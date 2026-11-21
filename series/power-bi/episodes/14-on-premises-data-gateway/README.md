# DEVLADLOG Power BI #14: On-Premises Data Gateway

Same **Contoso Bikes** data as episodes 1-13. Episode 9 had to read from SharePoint because the lab had no gateway; episode 11 already put the data in SQL Server on the
lab network (`CON-SQL01`, database `ContosoBikesDW`). This episode makes the **Power BI service** reach that server: a **standard mode gateway** on `CON-SRV02`, a data source, a bound semantic
model, a scheduled-refresh-capable import, and the checks that catch the three usual failures before anyone publishes.

Blog guide: <https://www.devladlog.com/articles/power-bi/2025-07-10-data-gateway-complete-guide-2025/>

What we build:

1. a **read-only SQL login** for the gateway (`sql/`), plus checks and tear-down
2. an import **M query** against `10.50.0.30` / `ContosoBikesDW` (`queries/sales-by-store.pq`) and `gateway/datasource.json`, the one definition of the data source
3. **`GatewayOps`**, a PowerShell 7 module: network test for the gateway machine, gateway and data source listing, the **server and database match check**, data source creation, binding, refresh and wait, and the `SqlTrustedServers` setting
4. **`gateway-credential`**, a small .NET 8 tool that writes the *Create Datasource* body with the credentials **encrypted by the Power BI SDK's own encryptor**
5. two scripts: `Test-GatewayHost.ps1` (run on the gateway machine) and `Register-LabDataSource.ps1`

| Path | What it is |
|---|---|
| [`src/sql/`](src/sql) | `01-gateway-login.sql` (login + `db_datareader`, password as a sqlcmd variable), `02-checks.sql`, `99-teardown.sql` |
| [`src/queries/sales-by-store.pq`](src/queries/sales-by-store.pq), [`src/gateway/datasource.json`](src/gateway/datasource.json) | The query and the gateway data source it must match (a test compares them) |
| [`src/ps/GatewayOps/`](src/ps/GatewayOps) | The module, 13 functions. Findings GW001 (error: no data source with exactly this server and database), GW002 (info: parameterised source), GW003 (info: match) |
| [`src/ps/Test-GatewayHost.ps1`](src/ps/Test-GatewayHost.ps1), [`Register-LabDataSource.ps1`](src/ps/Register-LabDataSource.ps1) | Network check for the gateway machine; check + create data source + optional bind (`-WhatIf` sends nothing) |
| [`src/GatewayCredential/`](src/GatewayCredential) | `gateway-credential` (.NET 8, `Microsoft.PowerBI.Api` 4.22.0): `--public-key-file`, `--self-test`; password only from `GATEWAY_DS_PASSWORD` |
| [`src/tools/expected.py`](src/tools/expected.py), [`src/data/star/`](src/data/star) | What the refresh must load: 4,071 lines, 1,862,401.98, five stores. The two CSVs are episode 11's (a test compares them byte for byte) |
| [`tests/GatewayOps.Tests.ps1`](tests/GatewayOps.Tests.ps1), [`tests/fixtures/rest/`](tests/fixtures/rest) | Pester: 24 tests, REST cmdlet mocked with Learn-shaped responses (zero GUIDs) |
| [`tests/test_project.py`](tests/test_project.py), [`tests/test_script.py`](tests/test_script.py) | pytest: 11 + 5 tests (query vs data source definition, T-SQL syntax, numbers, no secrets or real GUIDs, module manifest; the script follows the brief and its code scenes are real excerpts) |

## Run it

```bash
cd src
python3 tools/expected.py                  # 4,071 order lines, Sales Amount 1,862,401.98, 5 stores (+ per store)
dotnet build GatewayCredential -m:1 -v q
dotnet GatewayCredential/bin/Debug/net8.0/gateway-credential.dll --self-test
#   10 PASS (1024-bit key), 1 SKIP: the SDK's encryptor for keys above 1024 bits needs Windows CNG, so the 2048-bit case runs on the Windows laptop
cd ..
pip install --user pyyaml sqlglot pytest    # once
python3 -m pytest tests -q                 # 16 passed
pwsh -NoProfile -Command "Invoke-Pester ./tests/GatewayOps.Tests.ps1"   # 24 passed (Pester 6.2.0), 0 skipped after the dotnet build
```

The M query was also parsed with Microsoft's Power Query parser through episode 9's `pq-lint` (`1 queries: 0 error(s), 0 warning(s)`; that build is not part of this folder).
Delete `src/GatewayCredential/bin` and `obj` afterwards.

**Needs the lab and the tenant** ([demo.md](demo.md)): the gateway installation and registration, the data source, the binding, the refresh, `Get Gateways`, the real `Create Datasource`, the SQL scripts on SQL Server,
the network test on the real gateway machine. The container has no SQL Server, no gateway and no tenant. (`Test-GatewayHost.ps1` was run here only to see its output: the container's network says nothing about the lab.)

## What we learned / gotchas

- **Names must match exactly.** Learn ("Manage a SQL Server data source"): the link between the model and the gateway data source is the server name and the database name; they must match exactly and
  matching is **case-sensitive**. An IP address in Desktop needs the IP address on the gateway, `SERVER\INSTANCE` needs `SERVER\INSTANCE`. That is why the lab query uses `10.50.0.30` and not `CON-SQL01` (and the laptop may not resolve the lab DNS).
  `Test-DataSourceMatch` says which case it is: different case, different server text, or no data source.
- **Where it can go.** Learn: not on Server Core, not on Windows containers, not on a domain controller, not on a laptop that sleeps; Windows 10/11 or Server 2019/2022/2025, .NET Framework 4.8; recommended 8 cores and 8 GB, an SSD for spooling.
  One standard-mode and one personal-mode gateway per machine at most. A cluster (same version on every member) avoids a single point of failure. The lab VM is smaller than the recommendation; the README of a real deployment shouldn't copy that.
- **Outbound only.** TCP 80, 443, 1433, 5671, 5672 and 9350-9354, no inbound ports. Most of the list is wildcard names (`*.servicebus.windows.net`), so only six names can be tested from a script; for the Azure Relay ports Learn points to
  the gateway app's **Diagnostics > Network ports test**. New installations default to HTTPS mode for Azure Relay; the gateway falls back to HTTPS when TCP doesn't work.
- **The gateway must reach the source too.** `Test-GatewayHost.ps1` tests `10.50.0.30:1433` from the gateway machine, not from the laptop.
- **Encrypted credentials.** Learn: on-premises data source credentials must be encrypted with the gateway public key (`encryptedConnection: Encrypted`, `encryptionAlgorithm: RSA-OAEP`). We use the SDK's `AsymmetricKeyEncryptor`
  instead of writing our own crypto. Two things we hit: with `Microsoft.PowerBI.Api` 4.22.0 a key above 1024 bits goes through `RSACng` and **throws `PlatformNotSupportedException` off Windows** (so the Linux test uses 1024 bits, the laptop covers 2048);
  and 5.x of the package is a different SDK (no `Microsoft.Rest`), so the code is pinned to 4.22.0. Learn's *Create Datasource* page spells the body field `dataSourceName` in its table and `datasourceName` in its samples; the SDK sends `dataSourceName`.
  VNet and cloud gateways aren't supported by this API, and OAuth2 isn't a supported credential type here.
- **Binding.** Learn: add the API caller as a data source user first; without data source IDs the model binds to the first matching data source. A model with several sources needs **every** source on the gateway or the gateway isn't offered.
  **Republishing removes the association** (the dataset owner must associate again): bind in the pipeline after each publish. A new data source can take several minutes before it's usable.
- **Self-signed certificate.** Learn (SQL Server connector, troubleshooting): a refresh can fail with *The certificate chain was issued by an authority that is not trusted* when SQL Server uses a self-signed certificate. For the gateway the setting is
  `SqlTrustedServers` in `Microsoft.PowerBI.DataMovement.Pipeline.GatewayCore.dll.config` (comma separated, `*` wild card, back up the file first); for Desktop the environment variable `PBI_SQL_TRUSTED_SERVERS`. Learn also lists getting a certificate from a well-known CA.
  `Set-GatewaySqlTrustedServer` edits only an existing setting and refuses a file without it; its tests use a fixture shaped like Learn's snippet, not the real file.
- **Refresh history** gives `status` (`Unknown` while running, `Completed`, `Failed`, `Disabled`) and an `errorCode` inside `serviceExceptionJson`; `Start-DatasetRefreshAndWait` returns both. Learn's example code is `ModelRefreshFailed_CredentialsNotSpecified`.

## Not verified

- No gateway was installed, no data source created, no refresh run: the container has neither Windows, SQL Server nor a tenant. Everything REST is tested against mocks shaped like Learn's samples.
- The 2048-bit encryption path (Windows only), and which key size the gateway returns.
- That the service accepts the body written by the SDK exactly as it is (the API page is internally inconsistent about the name field).
- The T-SQL was parsed (sqlglot) but never run; the M was parsed but never run in Desktop.
- Whether the lab SQL Server triggers the certificate error, and whether `SqlTrustedServers` plus a restart fixes it; whether the real config file has the setting in the shape of the fixture.
- Learn's current steps for removing a gateway (the tear-down says to check them).

## References

- Install a gateway (requirements, standard mode, clusters, recovery key): <https://learn.microsoft.com/en-us/data-integration/gateway/service-gateway-install>
- Communication settings (ports, endpoints, network ports test, HTTPS mode): <https://learn.microsoft.com/en-us/data-integration/gateway/service-gateway-communication>
- Manage a SQL Server data source (names must match): <https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-enterprise-manage-sql>
- Add or remove a gateway data source: <https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-data-sources>; import and scheduled refresh: <https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-enterprise-manage-scheduled-refresh>
- Troubleshoot gateways (the "no access via an on-premises data gateway" error): <https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem-tshoot>
- SQL Server connector, certificate not trusted, `SqlTrustedServers`: <https://learn.microsoft.com/en-us/power-query/connectors/sql-server#troubleshooting>
- Configure credentials programmatically (encryption): <https://learn.microsoft.com/en-us/power-bi/developer/embedded/configure-credentials>
- REST: [Get Gateways](https://learn.microsoft.com/en-us/rest/api/power-bi/gateways/get-gateways), [Create Datasource](https://learn.microsoft.com/en-us/rest/api/power-bi/gateways/create-datasource), [Get Datasources In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasources-in-group),
  [Bind To Gateway In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/bind-to-gateway-in-group), [Refresh Dataset In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group), [Get Refresh History In Group](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-history-in-group)
- Gateway PowerShell cmdlets (`DataGateway` module, not used here): <https://learn.microsoft.com/en-us/powershell/gateway/overview>
