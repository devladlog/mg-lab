# DEVLADLOG Dynamics 365 #12 — Finance & Operations with Business Central

> **Reworked.** The first version of this episode read Dynamics 365 *Finance and Operations* over OData. There is no Finance
> trial for the lab and Microsoft's self-service Business Central trial is not offered for Portugal (owner's decision, not a
> Learn claim), so the live demo is now **Business Central in a local developer container** on the Windows recording
> laptop, built with Microsoft's BcContainerHelper module (sandbox artifacts, CRONUS demo company). Finance and Operations
> stays in the episode as **one labelled architecture scene**: what it is, and what differs from Business Central. Nothing here
> was run against Finance and Operations.

The back-office end of the Contoso story. **bckit**, a small Python tool, reads Business Central over its **API v2.0** and checks
that the customer there is the same customer as in Dataverse (the Dynamics 365 Sales trial environment):

- **doctor**: one call to the API root and one to `companies`, so a stopped container, a wrong URL or a refused login shows up first
- **companies / customers**: companies in the container, customers per company (type, currency, blocked)
- **invoices**: sales invoices with `$filter` on status and customer, `$orderby`, `$top`, and the remaining amount per customer
- **seed**: creates the fictional demo customers (Contoso Retail, Contoso Logistics Ltd, Contoso Hospitality Group, and one person)
  in the container; idempotent (skips a display name that already exists), `--dry-run`
- **reconcile**: Business Central customers against Dataverse accounts by number = `accountnumber`. R001 company customer with no
  Dataverse account (error), R002 Dataverse account with a number and no Business Central customer (warning), R003 names differ
  (warning), R004 the same number in several companies (warning), R005 people left out, they are contacts (info), R006 customer
  blocked in Business Central (info). Exit 1 on errors. `--name-contains` scopes both sides, so CRONUS' own sample customers don't
  bury the demo

Reads and one write path (`seed`, container only); nothing is written to Dataverse. `customers` and `reconcile` also run offline on the
saved shapes in [`sample/`](sample/) (`--bc-json`, `--dv-json`).

| Path | What it is |
|---|---|
| [`setup/New-LabBusinessCentral.ps1`](setup/New-LabBusinessCentral.ps1) | Checks Docker Desktop (installed, running, Windows-containers mode, with the switch instructions), installs/imports BcContainerHelper, `Get-BcArtifactUrl` for the current sandbox, `New-BcContainer` `mglab-bc` with NavUserPassword, proves the API with a real call, stores the generated admin password DPAPI-encrypted under `E:\MGLab\secrets\`. Idempotent; `-Remove` tears down; `-SetEnv` loads `BC_*` into the session without printing the password |
| [`bc.json`](bc.json) | API version, default URL, selected columns, the seed customers, the Dataverse table |
| [`src/bckit/bc.py`](src/bckit/bc.py) | API v2.0 client: URL builder (`companies(id)`, `$select`, `$filter`, `$orderby`, `$top`), `Prefer: odata.maxpagesize`, `@odata.nextLink` paging with a loop guard, 429/503 + Retry-After (a POST is retried on 429 only), readable errors with Learn hints (401, 404, 405, unreachable container) |
| [`src/bckit/customers.py`](src/bckit/customers.py) | Companies, customers, sales invoices, `seed`, and the Dataverse account reader |
| [`src/bckit/reconcile.py`](src/bckit/reconcile.py) | Rules R001-R006 and the summary |
| [`src/bckit/cli.py`](src/bckit/cli.py), [`auth.py`](src/bckit/auth.py), [`dataverse.py`](src/bckit/dataverse.py), [`findings.py`](src/bckit/findings.py) | CLI; MSAL token for Dataverse only (Business Central uses basic auth in the container); minimal Dataverse reader; finding type |
| [`sample/`](sample/) | `bc-customers.json` (6 fictional customers in two companies) and `dv-accounts.json` (4 accounts) |
| [`tests/`](tests/) | 36 pytest tests (API client, paging, retries, seed, reconcile, CLI, `script.yaml` checks) and 34 Pester tests for the setup script. The services are stubs/mocks in the tests only; the demo runs against the real container and Dataverse |

## Run and test (no tenant, no Docker)

```bash
cd series/dynamics-365/episodes/12-finance-operations
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                                  # 36 passed
pwsh -NoProfile -Command "Invoke-Pester -Path tests/New-LabBusinessCentral.Tests.ps1 -Output Normal"   # 33 passed, 1 skipped (DPAPI round trip: Windows only)
cd src
python3 -m bckit customers --bc-json ../sample/bc-customers.json --limit 3
python3 -m bckit reconcile --bc-json ../sample/bc-customers.json --dv-json ../sample/dv-accounts.json   # exit 1
```
```
Business Central: 6 customer(s) in 2 company(ies) (CRONUS USA, Inc., Contoso Test Co); 5 of type Company
Dataverse: 4 account(s) with an account number

WARNING R004  10000: exists in 2 companies (CRONUS USA, Inc., Contoso Test Co)
WARNING R003  20000: name differs: Business Central 'Contoso Logistics Ltd', Dataverse 'Contoso Logistics Holdings'
ERROR   R001  30000: 'Contoso Hospitality Group' (CRONUS USA, Inc.) has no Dataverse account with this account number
INFO    R006  40000: 'Contoso Energy' is blocked in Business Central (Invoice)
WARNING R002  99000: Dataverse account 'Contoso Legacy Store' has no Business Central customer
INFO    R005  Person: 1 customer(s) of type Person skipped (contacts, not accounts)
1 error(s), 3 warning(s), 2 info
```
(The numbers and the second company in `sample/` are made up for the sample.) The one tool call that did hit a socket in this
build was `BC_PASSWORD=x python3 -m bckit --bc-url http://127.0.0.1:9 doctor`: the real "cannot reach ... Is the container running
(docker ps)" error line, exit 1. The PowerShell script was also started for real on Linux and stops at its first check ("run it on
the Windows recording laptop").

## Against the real container (needs the recording laptop)

Details, sizes and the screen list are in [demo.md](demo.md). In short, on the Windows laptop:

```powershell
# elevated Windows PowerShell 5.1, Docker Desktop running
.\setup\New-LabBusinessCentral.ps1 -AcceptEula         # first run downloads ~15 GB; prints the company names, never the password
.\setup\New-LabBusinessCentral.ps1 -SetEnv             # BC_BASE_URL, BC_USER, BC_PASSWORD for this session
$env:DATAVERSE_URL = 'https://<org>.crm4.dynamics.com'  # reconcile only; sign-in is interactive
cd src
python -m bckit doctor
python -m bckit seed --company "CRONUS USA, Inc."
python -m bckit customers --company "CRONUS USA, Inc."
python -m bckit invoices --company "CRONUS USA, Inc." --status Open
python -m bckit reconcile --name-contains Contoso
```

## Finance and Operations vs Business Central (the architecture scene)

What the first version of the episode established from Learn, kept as context (only the Business Central column was run):

| | Finance and Operations apps | Business Central (this demo) |
|---|---|---|
| Endpoint | `<environment URL>/data/<entity>` (OData, e.g. `CustomersV3`) | `<host>:7048/<instance>/api/v2.0/companies(<id>)/<resource>` in a container |
| Company | default company only, unless `cross-company=true`; `$filter=dataAreaId eq '<id>'` | every resource is under `companies(<id>)` |
| Page size | server-driven, max 10,000, follow `@odata.nextLink` | default max 20,000 (online: fixed), `Prefer: odata.maxpagesize`, follow `@odata.nextLink` |
| Throttling | 429 + Retry-After (service protection limits) | 429, and 503 when the queue times out (online limits); on-premises the connection limits default to 0 (unlimited) |
| Sign-in | Entra app registered in Entra **and** inside the app | Entra OAuth online; basic auth (web service access key) on-premises/containers only |
| With Dataverse | dual-write (map *Customers V3 (accounts)*: `CustomerAccount` to `accountnumber`), virtual tables | data synchronization (Customer to Account, couplings), virtual tables over the Business Central API |

## What we learned / gotchas

- **Docker must be in Windows-containers mode.** Learn (*Running a container-based development environment*): Docker Desktop
  uses Linux containers by default; right-click the Docker icon, *Switch to Windows Containers*. The script reads `docker info
  --format '{{.OSType}}'` and prints that instruction when it says `linux`.
- **Size.** Learn: containers use at least 6 GB of memory and artifacts plus images take about 15 GB of disk; the helper's cache is
  `C:\bcartifacts.cache` and working files go under `C:\ProgramData\BCContainerHelper`. The script sets `-memoryLimit 8G`
  (the BcContainerHelper source defaults Hyper-V isolation to 8G). `-Isolation hyperv` passes `-isolation hyperv`, Learn's suggestion if creation fails.
- **PowerShell edition.** Learn: for version 28.0 containers use Windows PowerShell 5.1 for management functions; PowerShell 7 has a
  known issue loading the Business Central admin modules. The script refuses PowerShell 7 unless `-AllowPowerShell7`.
- **Artifacts.** `Get-BcArtifactUrl -type Sandbox -country us -select Latest` is Learn's quick start; the source documents `-select`
  values (`Latest`, `Current`, `NextMajor`, ...) and `-version`. Insider builds need `-accept_insiderEula`; not used.
- **API switched on.** Learn (*Enabling the APIs*, on-premises): `ODataServicesEnabled` and `ApiServicesEnabled` must be true,
  otherwise calls return 405. In the BcContainerHelper source `New-BcContainer` adds `--env enableApiServices=Y` for Business Central 12
  and later, so the script does not touch the server instance: it **proves** the API with a call and prints the Learn hint on 405.
- **Hosts and SSL.** `-updateHosts` writes the container name to the hosts file (Learn); `Remove-BcContainer` removes that entry
  again (source). Without `-useSSL` the container speaks plain HTTP, which is why the default URL is `http://mglab-bc:7048/BC`.
- **Authentication.** Learn (*Web services authentication*, *Endpoints*): on-premises basic authentication is the user name plus the
  *web service access key* as password; it is deprecated in Business Central online (use OAuth). `bckit` sends the container password;
  `doctor` and the script print the access-key hint on a 401 (see "Not verified").
- **Premium plan.** Learn (*Working with development sandboxes and entitlements*): `-assignPremiumPlan` gives the admin user the Premium
  plan; the script passes it.
- **Secret handling.** Learn (*ConvertFrom-SecureString*): without a key the Windows Data Protection API encrypts the string; on
  non-Windows systems a SecureString is not encrypted, so `Save-LabSecret` refuses to run there. The file
  `E:\MGLab\secrets\mglab-bc.admin.dpapi` is readable only by the same Windows user on the same machine; the password is never printed
  and never inside the repository.
- **Company id everywhere.** Learn (*API endpoint structure*, *Tips for working with APIs*): all resources live under a company; the
  company can be in the path or `?company=`. `bckit` uses the path form.
- **Customers.** Learn (*customer resource type*): `type` is `Company` or `Person`, `blocked` is `' '`, `Ship`, `Invoice` or `All`. The POST
  example returns the assigned `number`, so `seed` prints it instead of choosing one. A number is unique per company, not across companies.
- **Sales invoices.** Learn (*salesInvoice resource type*): status is `' '`, `Draft`, `In Review`, `Open`, `Paid`, `Canceled` or `Corrective`, and the
  `id` of the API resource can differ from the record's `systemId` for posted invoices.
- **Paging.** Learn (*Server-driven paging*): default 20,000 per page; `odata.maxpagesize` can't exceed the server setting (on-premises) or
  20,000 (online); a client that follows `@odata.nextLink` doesn't care.
- **Throttling locally.** Learn (*Operational limits*): online, too many requests get 429 and a full queue times out with 503; on-premises
  `ODataMaxConnections` defaults to 0 (no limit). The retry code is for online environments; against the container it will rarely fire.
- **How Business Central talks to Dataverse.** Learn (*Synchronizing data in Business Central with Dataverse*): the standard mapping couples
  Customer with Account (Business Central filter: *Blocked* is blank; Dataverse filter: relationship type Customer and active) and
  Contact with Contact; virtual tables read the Business Central API without copying. Business Central **online** connects only to Dataverse
  environments of the same Entra tenant (the rule does not apply on-premises). The container here is **not** connected to Dataverse:
  `reconcile` is a code-level check with our own key (customer number = `accountnumber`, the same key the Finance dual-write map used), not
  something Learn prescribes for Business Central couplings.
- **Not verified (checked on the laptop, demo.md steps 3 and 6, then fix the code and tests from the real output).** That the container
  answers at `http://mglab-bc:7048/BC/api/v2.0` (server instance name `BC`, HTTP, port 7048 are defaults from the source and Learn's
  examples); that the generated NavUserPassword password is accepted as the basic-auth password (Learn documents the web service access
  key; if it is refused, create one in the web client and set `BC_PASSWORD` to it); that the US sandbox has more than one company; the
  numbers Business Central assigns to the seeded customers; that process isolation works on the laptop's Windows build (otherwise run the script with
  `-Isolation hyperv`, Learn's first suggestion); whether the sales-trial Dataverse accounts already carry account numbers.

## References
- [Running a container-based development environment](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-running-container-development) (Docker mode, memory and disk, `Get-BcArtifactUrl`, `New-BcContainer`, `-updateHosts`, PowerShell 5.1 note) and [BcContainerHelper](https://github.com/microsoft/navcontainerhelper) (`New-BcContainer`, `Get-BcArtifactUrl`, `Remove-BcContainer` sources)
- [Working with development sandboxes and entitlements](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-work-sandbox-entitlements) (`-assignPremiumPlan`)
- [Endpoints for the APIs](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/endpoints-apis-for-dynamics), [API endpoint structure](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/webservices/api-endpoint-structure), [Enabling the APIs (on-premises)](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/enabling-apis-for-dynamics-nav), [Tips for working with APIs](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-connect-apps-tips), [Using filters](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-connect-apps-filtering)
- Resources: [company](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/resources/dynamics_company), [customer](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/resources/dynamics_customer), [create customer](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/api/dynamics_customer_create), [salesInvoice](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/resources/dynamics_salesinvoice)
- [Web services authentication](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/webservices/web-services-authentication) and [Get started developing Connect apps](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-develop-connect-apps) (basic auth with the web service access key, on-premises only)
- [Server-driven paging in OData web services](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/webservices/server-driven-paging-in-odata-web-services), [Operational limits for Business Central online](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/administration/operational-limits-online), [Configuring the server (outdated versions): OData settings](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/administration/configure-server-instance-archived)
- [Synchronizing data in Business Central with Dataverse](https://learn.microsoft.com/dynamics365/business-central/admin-synchronizing-business-central-and-sales), [Integrating Business Central with Dataverse](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/dataverse-integration-overview), [Integrate with Dataverse via data sync](https://learn.microsoft.com/dynamics365/business-central/admin-common-data-service)
- [Welcome to Business Central](https://learn.microsoft.com/dynamics365/business-central/welcome) (small and mid-sized organizations)
- [ConvertFrom-SecureString](https://learn.microsoft.com/powershell/module/microsoft.powershell.security/convertfrom-securestring) (DPAPI when no key is given)
- Finance and Operations context (architecture scene, from the first version): [Open Data Protocol (OData)](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/odata), [Service endpoints overview](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/services-home-page), [Service protection API limits](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/service-protection-api-limits), [Dual-write overview](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/dual-write-overview), [Mapping reference](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/mapping-reference)
- Blog: [Dynamics 365 Finance & Operations — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-16-dynamics-365-finance-operations-complete-guide-2025/)
