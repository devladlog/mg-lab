# DEVLADLOG Azure #7 — Storage & Databases: the right store, no secrets, retries that can't duplicate

Episodes 1–5 kept contoso's orders as blobs. This episode gives each kind of data the store it needs:

- **Orders** (relational, transactional, queried by customer): **Azure SQL Database free tier**
  (General Purpose serverless, 100,000 vCore seconds + 32 GB data + 32 GB backup per database per month,
  auto-pause at the limit). **Microsoft Entra-only authentication**: the server has no SQL login and no password;
  the API connects with `Authentication=Active Directory Default`
- **Invoices** (documents, written once, read rarely, kept for years): **Blob Storage** with **shared keys
  disabled**, soft delete, and a **lifecycle policy** Hot → Cool (30 d) → Cold (90 d) → delete (10 years, an example).
  Downloads use a short-lived, read-only **user delegation SAS** (the only SAS that still works without keys)
- **Correctness under retries**: EF Core's retrying execution strategy (the free tier auto-pauses after 15 minutes and
  the first connection fails with **40613** while it resumes) + a **unique `IdempotencyKey` index**, so a retried
  INSERT becomes a replay, not a second order. **Keyset paging** and **optimistic concurrency** (ETag / If-Match)

```
 client ──POST /orders (Idempotency-Key)──► API (.NET 10, EF Core 10) ──Entra token──► Azure SQL free tier (Entra-only)
                                              │                                        Orders + OrderLines, unique key index
                                              └─ invoice JSON ──Entra token──► Blob "invoices/2026/11/<id>.json" (keys off)
 client ──GET /orders/{id}/invoice──► user delegation SAS (read, this blob, HTTPS, 10 min) ──► download straight from Blob
 lifecycle: Hot ──30 d──► Cool ──90 d──► Cold ──3650 d──► deleted          soft delete 7 days
```

| Path | What it is |
|---|---|
| [`src/Contoso.Orders.Api/Program.cs`](src/Contoso.Orders.Api/Program.cs) | Minimal API: `POST /orders`, `GET /orders/{id}`, `GET /customers/{id}/orders?after=&take=`, `POST /orders/{id}/cancel` (If-Match), `GET /orders/{id}/invoice`, `/healthz`; `--print-schema`, `--create-schema` |
| [`src/.../Data/DatabaseSetup.cs`](src/Contoso.Orders.Api/Data/DatabaseSetup.cs) | Azure SQL connection string (Entra ID, Encrypt, Connect Timeout 60), `EnableRetryOnFailure`, SQLite for local runs, schema script |
| [`src/.../Data/OrdersDbContext.cs`](src/Contoso.Orders.Api/Data/OrdersDbContext.cs) | Model: identity key, unique `IdempotencyKey`, `(CustomerId, CreatedUtc DESC, Id DESC)` index, `Version` concurrency token |
| [`src/.../Orders/OrderService.cs`](src/Contoso.Orders.Api/Orders/OrderService.cs) | Idempotent create (replay / conflict / race via unique violation 2601/2627), keyset paging, optimistic cancel |
| [`src/.../Orders/OrderRules.cs`](src/Contoso.Orders.Api/Orders/OrderRules.cs) | Episode 1's catalogue and rules, request hash |
| [`src/.../Invoices/BlobInvoiceStore.cs`](src/Contoso.Orders.Api/Invoices/BlobInvoiceStore.cs) | Invoice upload; user delegation SAS (read, `sr=b`, HTTPS, ≤ 1 h) with a cached delegation key |
| [`db/schema.sql`](db/schema.sql) | T-SQL generated from the model (`--print-schema`); a test fails if it drifts |
| [`db/demo-queries.sql`](db/demo-queries.sql) | Query editor script for the demo: identity, orders, no duplicate keys, sessions that block auto-pause |
| [`infra/main.bicep`](infra/main.bicep) + [`main.bicepparam`](infra/main.bicepparam) | Storage (keys off, soft delete, lifecycle, role), SQL server (Entra-only), firewall rule for one IP, free-tier database |
| [`infra/deploy.sh`](infra/deploy.sh) / [`run-api.sh`](infra/run-api.sh) / [`smoke.sh`](infra/smoke.sh) / [`teardown.sh`](infra/teardown.sh) | what-if → deploy → free-tier check → create schema; run the API against Azure; the walkthrough; delete the group |
| [`tests/Contoso.Orders.Tests`](tests/Contoso.Orders.Tests) | 47 xUnit tests (below) |

## Build and test (here, no Azure needed)

```bash
cd tests/Contoso.Orders.Tests
dotnet test            # Passed!  - Failed: 0, Passed: 47, Skipped: 0, Total: 47
#   OrderServiceTests 13  SQLite in memory: pricing, replay, conflict, unknown SKU, the unique index rejects a 2nd row,
#                         FK error is not a "duplicate", keyset paging with equal timestamps, cursor, optimistic concurrency
#   RulesTests         7  shape validation, request hash ignores line order
#   ApiTests           7  WebApplicationFactory: 400/201/200 replay/409/422/428/412, paging cursor, invoice 503 when not configured
#   DatabaseSetupTests 5  Entra-only connection string (no user/password, Encrypt, 60 s), retrying strategy, schema.sql up to date
#   InvoiceStoreTests  7  Azurite over HTTPS with OAuth: upload, user delegation SAS download, tampered SAS 403, SAS can't write,
#                         overwrite on retry, lifetime cap, delegation key reuse and renewal
#   BicepTests         8  keys off, lifecycle order + minimum days, soft delete, Entra-only SQL, free tier + AutoPause, one-IP rule, role, no secrets

cd ../../infra
bicep lint main.bicep  # clean (bicepconfig.json rules at error)
ADMIN_OBJECT_ID=00000000-0000-0000-0000-000000000000 ADMIN_LOGIN=alex.demo@contoso.com CLIENT_IP=203.0.113.10 \
  bicep build-params main.bicepparam --stdout > /dev/null
bash -n deploy.sh run-api.sh smoke.sh teardown.sh
```

Verified in this container (.NET SDK 10.0.115, EF Core 10.0.15, Azure.Storage.Blobs 12.27.0, Bicep 0.49.2,
Azurite 3.38.0 via `npx`, node 22; the test certificate is made in .NET, no openssl): 47 passed. The `InvoiceStoreTests` start Azurite themselves
(`npx --yes --package azurite@3.38.0 azurite-blob … --oauth basic` with a throw-away self-signed certificate) and
sign in with an unsigned test JWT: Azurite's basic OAuth mode checks the claims and **verifies the user delegation SAS
signature**, so the SAS tests are real, only the token isn't. The API also ran locally on SQLite and
`infra/smoke.sh` passed every step up to the invoice (skipped: no storage locally). Mutation check: making the
`IdempotencyKey` index non-unique fails 3 tests (the database-rejects test and both schema tests).

**SQLite is not Azure SQL.** It runs the EF model, the unique index, the concurrency token and the paging query in
the tests; T-SQL behaviour, Entra sign-in, the 40613 resume and the free tier are only checked in Azure (demo.md).
**Not run here:** anything in Azure.

## Run locally (no Azure)

```bash
cd src/Contoso.Orders.Api
dotnet run -- --create-schema && dotnet run --urls http://localhost:5199     # SQLite file orders-local.db
../../infra/smoke.sh                                                         # invoice step is skipped
```

## Deploy, demo, tear down (needs a subscription)

```bash
az login
infra/deploy.sh rg-mglab-azure-07 westeurope     # what-if, deploy, free-tier check, schema as the Entra admin
infra/run-api.sh &                               # API on this laptop, signed in as you (az login)
infra/smoke.sh                                   # every check, including the invoice download through the SAS
infra/teardown.sh rg-mglab-azure-07
```

## What we learned / gotchas

- **A retried INSERT can create a second row.** Learn (EF Core connection resiliency): if the connection drops
  while a commit is acknowledged, the execution strategy retries as if it had rolled back, which with store-generated
  keys "could lead to data corruption". The unique `IdempotencyKey` index makes the retry fail with 2601/2627, and
  `OrderService` turns that into a replay of the order that did commit. Same path for two racing requests.
- **The free tier pauses after 15 minutes, and that delay can't be changed.** The first connection then fails with
  **40613** while the database resumes (Learn: generally under a minute). `EnableRetryOnFailure` retries it, and
  `Connect Timeout=60` follows the SqlClient guidance for serverless (a client-side timeout, error -2, isn't retried).
  Open query editor or SSMS sessions keep the database awake and burn free vCore seconds: close them.
- **At the free limit you choose: pause until next month, or pay.** `freeLimitExhaustionBehavior: AutoPause`; Learn says
  switching to "continue with charges" can't be switched back. A test pins `AutoPause`.
- **Entra-only means no `administratorLogin` at all.** With `azureADOnlyAuthentication: true` the template has no
  password parameter; the schema is created by the signed-in Entra admin (`--create-schema`). In production you'd add
  the app's managed identity as a contained user (`CREATE USER … FROM EXTERNAL PROVIDER`) with only data roles.
- **Shared keys off kills account and service SAS, not user delegation SAS.** Learn's table: user delegation SAS is
  permitted, service and account SAS are denied. The key that signs it comes from `GetUserDelegationKey`, needs a role
  with `generateUserDelegationKey` (Storage Blob Data Contributor has it) and lives at most seven days; the SAS can't
  outlive it. We fetch a 2-hour key and reuse it for many links, renewing before it can't cover a link (a test checks).
- **Azurite's OAuth check wants an `iat` claim.** The first fake token had `nbf`/`exp` only and every call failed
  with "Authentication scheme Bearer is not supported". (Hit while building the tests.)
- **Cool and Cold have minimum stays.** Moving or deleting a blob before 30 days in Cool or 90 days in Cold is charged
  as early deletion (prorated). The Bicep test checks the gaps between the lifecycle steps. New or changed policies take
  up to 24 hours to take effect, so the demo shows the rule, not a blob changing tier.
- **Keyset, not OFFSET.** The page query is `WHERE CreatedUtc < @t OR (CreatedUtc = @t AND Id < @id)` on an index
  with the same order. An `Id` tie-breaker matters: the test creates orders with equal timestamps.
- **No GUID clustered key.** `Id` is a `bigint IDENTITY`; the version GUID is only a concurrency token.

## References
- Blog: [Azure Storage & Databases — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-16-azure-storage-databases-complete-guide-2026/)
- [Build and test apps with the Azure SQL Database free tier](https://learn.microsoft.com/azure/azure-sql/database/free-offer) (allowances, 10 databases per subscription, `useFreeLimit`, `freeLimitExhaustionBehavior`, 15-minute fixed auto-pause, Free amount remaining metric)
- [Auto-pause and auto-resume in serverless](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-auto-pause-resume) (40613, retry logic, sessions that prevent auto-pause) and the [serverless FAQ](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-faq)
- [Microsoft.Data.SqlClient for SQL Server: production baseline](https://learn.microsoft.com/sql/connect/ado-net/microsoft-ado-net-sql-server) (ConnectTimeout ≥ 60 s for serverless)
- [Microsoft Entra-only authentication with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-azure-ad-only-authentication)
- [EF Core connection resiliency](https://learn.microsoft.com/ef/core/miscellaneous/connection-resiliency) (commit failure and the idempotency issue) and [`EnableRetryOnFailure`](https://learn.microsoft.com/dotnet/api/microsoft.entityframeworkcore.infrastructure.sqlserverdbcontextoptionsbuilder.enableretryonfailure) (6 retries, 30 s)
- [Microsoft SQL Server EF Core provider](https://learn.microsoft.com/ef/core/providers/sql-server/) (`UseAzureSql` sets resiliency automatically; we use `UseSqlServer` + `EnableRetryOnFailure` explicitly)
- [Prevent Shared Key authorization](https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent) (how each SAS type behaves)
- [Create a user delegation SAS with .NET](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-dotnet) and [the REST reference](https://learn.microsoft.com/rest/api/storageservices/create-user-delegation-sas) (seven-day key, fields, revocation)
- [Lifecycle management policy structure](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-policy-structure), [policy FAQ](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-policy-faq) (up to 24 hours) and [access tiers](https://learn.microsoft.com/azure/storage/blobs/access-tiers-overview) (early deletion: Cool 30 days, Cold 90 days)
- Prices in demo.md: [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (EUR, West Europe, queried 21 Nov 2026)
- Azurite (not on Learn for these flags): https://github.com/Azure/Azurite
