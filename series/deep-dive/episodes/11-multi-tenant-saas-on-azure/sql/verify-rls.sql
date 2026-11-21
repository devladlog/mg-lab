-- Proves the policy in a real database. Run as the SQL Entra admin in a database that already has
-- 001-schema.sql and 002-rls.sql. Everything happens inside one transaction that is rolled back at the end,
-- so it leaves nothing behind. Works on SQL Server 2022 and Azure SQL Database.
-- Expected: tenant A sees 2 rows, tenant B sees 1, no tenant sees 0, and the cross-tenant insert fails with error 33504.

SET NOCOUNT ON;
BEGIN TRANSACTION;

DECLARE @a uniqueidentifier = '00000000-0000-0000-0000-0000000000b1';
DECLARE @b uniqueidentifier = '00000000-0000-0000-0000-0000000000b2';

INSERT dbo.Tenants (TenantId, Name, [Plan], Status, CreatedUtc) VALUES
    (@a, N'Northwind Traders', N'business', N'active', SYSUTCDATETIME()),
    (@b, N'Adventure Works',   N'starter',  N'active', SYSUTCDATETIME());

-- Seed through the policy like the app does: set the tenant first (without @read_only so this script can switch).
EXEC sys.sp_set_session_context @key = N'TenantId', @value = @a;
INSERT dbo.PurchaseRequests (TenantId, Id, Title, Amount, Status, CreatedBy, CreatedUtc) VALUES
    (@a, NEWID(), N'Northwind laptops', 1200, N'submitted', N'oid-alex', SYSUTCDATETIME()),
    (@a, NEWID(), N'Northwind chairs',   300, N'submitted', N'oid-alex', SYSUTCDATETIME());
EXEC sys.sp_set_session_context @key = N'TenantId', @value = @b;
INSERT dbo.PurchaseRequests (TenantId, Id, Title, Amount, Status, CreatedBy, CreatedUtc) VALUES
    (@b, NEWID(), N'Adventure Works bikes', 800, N'submitted', N'oid-riley', SYSUTCDATETIME());

EXEC sys.sp_set_session_context @key = N'TenantId', @value = @a;
SELECT N'tenant A sees' AS step, COUNT(*) AS visible_rows FROM dbo.PurchaseRequests;

EXEC sys.sp_set_session_context @key = N'TenantId', @value = @b;
SELECT N'tenant B sees' AS step, COUNT(*) AS visible_rows FROM dbo.PurchaseRequests;

EXEC sys.sp_set_session_context @key = N'TenantId', @value = NULL;
SELECT N'no tenant sees (even as admin)' AS step, COUNT(*) AS visible_rows FROM dbo.PurchaseRequests;

-- A row for tenant B written while the session says tenant A: the block predicate must refuse it.
EXEC sys.sp_set_session_context @key = N'TenantId', @value = @a;
BEGIN TRY
    INSERT dbo.PurchaseRequests (TenantId, Id, Title, Amount, Status, CreatedBy, CreatedUtc)
    VALUES (@b, NEWID(), N'Planted by tenant A', 1, N'submitted', N'oid-alex', SYSUTCDATETIME());
    SELECT N'cross-tenant insert' AS step, N'NOT BLOCKED - the policy is not working' AS result;
END TRY
BEGIN CATCH
    SELECT N'cross-tenant insert' AS step, ERROR_NUMBER() AS error_number, ERROR_MESSAGE() AS result;
END CATCH;

ROLLBACK TRANSACTION;
