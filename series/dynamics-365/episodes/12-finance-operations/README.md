# DEVLADLOG Dynamics 365 #12 — Finance & Operations

The back-office end of the Contoso story. Contoso Retail, the account that came out of [episode 7](../07-dynamics-365-sales/)'s
lead and raised cases in [episode 8](../08-dynamics-365-customer-service/), also has to be invoiced, and that happens in
Dynamics 365 Finance. **fokit**, a small Python tool, reads Finance and Operations over its real OData endpoint and
checks that the customer there is the same customer as in Dataverse:

- **doctor**: gets a token and makes one small OData call (`CustomersV3?$top=1`), so a failed app registration or a wrong
  entity name shows up before anything else
- **customers**: customers over OData with `cross-company=true` (or one legal entity with a `dataAreaId` filter), count
  per company and the first rows
- **reconcile**: Finance customers against Dataverse accounts by account number, the same key the dual-write
  *Customers V3 (accounts)* map uses. R001 organization customer with no Dataverse account (error), R002 Dataverse
  account with an account number and no Finance customer (warning), R003 names differ (warning), R004 the same
  CustomerAccount in several companies (warning), R005 people (PartyType Person) left out, they belong to the contacts
  map (info). Exit 1 on errors

Read-only: nothing is written to Finance and Operations or to Dataverse. `customers` and `reconcile` also run offline on
the saved responses in [`sample/`](sample/) (`--fo-json`, `--dv-json`).

| Path | What it is |
|---|---|
| [`fo.json`](fo.json) | Entity (`CustomersV3`), columns, the PartyType value that means organization, the Dataverse table |
| [`src/fokit/fo.py`](src/fokit/fo.py) | OData client for Finance and Operations: URL builder (`$select`, `$filter`, `$top`, `cross-company`), `@odata.nextLink` paging, 429 + Retry-After |
| [`src/fokit/customers.py`](src/fokit/customers.py) | Fetch and normalize Customers V3 rows and Dataverse accounts |
| [`src/fokit/reconcile.py`](src/fokit/reconcile.py) | Rules R001-R005 and the summary |
| [`src/fokit/cli.py`](src/fokit/cli.py), [`auth.py`](src/fokit/auth.py), [`dataverse.py`](src/fokit/dataverse.py), [`findings.py`](src/fokit/findings.py) | CLI; MSAL tokens (client credentials or interactive; `AZURE_CLIENT_ID` is required, there is no shared sample id for Finance and Operations); minimal Dataverse reader; finding type |
| [`sample/`](sample/) | `fo-customers.json` (7 fictional customers in two companies) and `dv-accounts.json` (5 accounts) in the services' response shape |
| [`tests/`](tests/) | 17 pytest tests; the services are a recording stub (tests only: the demo runs against the real environments) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/12-finance-operations
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                                  # 17 passed
cd src
python3 -m fokit customers --fo-json ../sample/fo-customers.json --limit 3
python3 -m fokit reconcile --fo-json ../sample/fo-customers.json --dv-json ../sample/dv-accounts.json   # exit 1
```
```
finance and operations: 7 customer(s) in 2 company(ies) (dem2, demf); 6 organization(s)
Dataverse: 5 account(s) with an account number

WARNING R004  C-1001: exists in 2 companies (demf, dem2)
WARNING R003  C-1004: name differs: F&O 'Contoso Energy', Dataverse 'Contoso Energy Holdings'
ERROR   R001  C-3001: 'Contoso Marine' (dem2) has no Dataverse account with this account number
WARNING R002  C-1099: Dataverse account 'Contoso Legacy Store' has no finance and operations customer
INFO    R005  Person: 1 customer(s) with PartyType Person skipped (contacts map, not accounts)
1 error(s), 3 warning(s), 1 info
```

## Against the services (needs tenant)

Prerequisites (details in [demo.md](demo.md)): a Finance environment (the lab uses a subscription-based trial created in the
Power Platform admin center), a Microsoft Entra app registered **both** in Entra ID and inside Finance and Operations, a
Dataverse environment with accounts.

```bash
export FO_URL=https://<environment>.operations.dynamics.com
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
export AZURE_TENANT_ID=<tenant id> AZURE_CLIENT_ID=<app id> AZURE_CLIENT_SECRET=<secret>   # secret optional: leave it out for an interactive sign-in
cd src
python3 -m fokit doctor
python3 -m fokit customers
python3 -m fokit customers --company usmf
python3 -m fokit reconcile
```

## What we learned / gotchas

- **Getting an environment.** Learn (*Unified admin trials*): free subscription-based trials exist for Finance, Supply
  Chain Management, Project Operations and Commerce; a tenant admin gets the trial license from the Marketplace in the
  Microsoft 365 admin center, assigns it, then creates the environment in the Power Platform admin center (type *Trial
  (subscription-based)*, *Enable Dynamics 365 apps*, the Finance template). Deployment can take an hour, and the trial
  does not support development with Visual Studio. New customers can no longer create Lifecycle Services projects for
  Finance and similar apps (from February 2026): use the Power Platform admin center.
- **Two registrations.** Learn (*Service endpoints overview*): register an application in Microsoft Entra ID, then
  register its client id in Finance and Operations under *System administration > Setup > Microsoft Entra applications*
  with a user (the sample uses Admin; a dedicated service account is the better practice). The token is requested for the
  environment URL with no trailing slash. Both authorization code and client credentials (secret or certificate) are supported.
- **Default company only.** Learn (*OData*): without `cross-company=true` you get only the user's default company; with it,
  every company the user can access; `$filter=dataAreaId eq '<id>'` with it narrows to one.
- **OData limits worth knowing** (Learn): only entities marked `IsPublic` are exposed; you must provide all key fields to
  address one record; `$expand` is first-level only; `has` and `in` are not supported; `$skip` and `$top` exist but server-driven
  paging has a maximum page size of 10,000, so follow `@odata.nextLink`; batch requests are limited to 5,000 operations.
- **Customers V3 is the heavy entity.** Learn (*Customers V3 entity*): about 80 fields the other customer entities don't have,
  performance pattern *single thread only*, "do not use where high performance is required", and *Customer definitions* plus
  *Customer details V2* usually outperform it. We use Customers V3 because it is the entity the dual-write map uses; the
  entity name is a setting in `fo.json`.
- **Throttling.** Learn (*Service protection API limits*, *Throttling prioritization*): resource-based limits apply from
  version 10.0.19 on; the user-based limits (6,000 requests, 20 minutes of execution time, 52 concurrent requests per five
  minutes) are not implemented in current versions (disabled by default from 10.0.35, removed from 10.0.36). A throttled
  request gets 429 and Retry-After; retried requests get no priority over new ones. Throttling applies to OData and custom
  services only, not to the data management framework, recurring integrations or (with the Power Platform integration
  enabled) virtual tables. Priorities are set in *System administration > Setup > Throttling priority mapping* (needs System
  administrator or Integration priority manager). The Lifecycle Services query *Requests throttled* shows what was throttled.
- **Not for Power BI.** Learn (*Integration between finance and operations apps and third-party services*): don't use OData for
  Power BI reports, use the entity store.
- **Dual-write key.** Learn (*Enable table maps for dual-write*, *Dual-write mapping reference*): a table map needs an alternate
  key in Dataverse that matches the Finance key; for customers, `CustomerAccount` is mapped to `accountnumber`. The *Customers
  V3 (accounts)* map has the source filter `PartyType == "Organization"` (people go to *Customers V3 (contacts)*). Number
  sequences in the two systems are not connected, and merging accounts in Dataverse doesn't run while a dual-write map exists
  (Learn, *Dual-write FAQ*).
- **Power Platform integration is mandatory.** Learn (*Enable Power Platform integration*): since 1 May 2025 every Finance and
  Operations environment must have it enabled; unlinked environments get it enabled automatically, linked to a new or an
  existing Power Platform environment.
- **Not verified on Learn** (so demo.md step 6 checks them against the real environment and the code is fixed from its
  output): that `PartyType` comes back in the JSON as the string `Organization` (the code compares the text and treats anything
  else as a person); the exact property casing `dataAreaId` in the response (Learn shows it in `$filter`); that
  `$select` accepts all six columns in `fo.json` on this entity; and whether `@odata.nextLink` appears for Customers V3 at the
  environment's page size. The Learn field table writes the currency column as `SALECURRENCYCODE`; the CDM reference and
  our `$select` use `SalesCurrencyCode`.

## References
- [Open Data Protocol (OData)](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/odata) (IsPublic, key fields, query options, paging 10,000, cross-company, batch)
- [Service endpoints overview](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/services-home-page) (authentication, app registration, Microsoft Entra applications form, resource URL without trailing slash)
- [Customers V3 entity](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-customers-v3-customerv3) (CustomersV3, required fields, performance) and [Customer definitions entity](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-customer-definitions-customerbase)
- [Service protection API limits](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/service-protection-api-limits), [Retry operations](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/service-protection-retry-operations), [Throttling prioritization](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/priority-based-throttling), [Maximize API throughput](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/service-protection-maximizing-api-throughput), [Monitor API throttling](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/service-protection-monitoring)
- [Integration between finance and operations apps and third-party services](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/integration-overview) (OData scenarios, not for Power BI)
- [Dual-write overview](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/dual-write-overview), [Enable table maps](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/enable-entity-map), [Mapping reference](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/mapping-reference), [Dual-write FAQ](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/dual-write-faq)
- [Unified developer experience for finance and operations apps](https://learn.microsoft.com/power-platform/developer/unified-experience/finance-operations-dev-overview) (dual-write vs virtual tables), [Microsoft Power Platform integration](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/power-platform/overview), [Enable Power Platform integration](https://learn.microsoft.com/dynamics365/fin-ops-core/dev-itpro/power-platform/enable-power-platform-integration)
- [Unified admin trials](https://learn.microsoft.com/power-platform/admin/unified-experience/admin-trials) and [About trial environments](https://learn.microsoft.com/power-platform/admin/trial-environments)
- Blog: [Dynamics 365 Finance & Operations — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-16-dynamics-365-finance-operations-complete-guide-2025/)
