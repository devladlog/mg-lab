-- Row-level security: the database refuses to show or write another tenant's rows,
-- even when the application forgets a WHERE clause. Run ONCE as the SQL Entra admin, after 001-schema.sql.
-- While a policy is OFF or dropped the table is unprotected (Learn: users then see all rows). To change a predicate,
-- use ALTER SECURITY POLICY ... ALTER FILTER PREDICATE / ALTER BLOCK PREDICATE (Learn: ALTER SECURITY POLICY, examples D and E),
-- not STATE = OFF.
-- The application stores the tenant with sp_set_session_context (@read_only = 1) when it opens a connection.
-- No tenant in the session means no rows: the policy fails closed.

IF SCHEMA_ID(N'Security') IS NULL EXEC (N'CREATE SCHEMA Security');
GO

CREATE FUNCTION Security.fn_tenant_predicate (@TenantId uniqueidentifier)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS allowed
       WHERE @TenantId = CAST(SESSION_CONTEXT(N'TenantId') AS uniqueidentifier);
GO

CREATE SECURITY POLICY Security.TenantIsolation
    ADD FILTER PREDICATE Security.fn_tenant_predicate(TenantId) ON dbo.PurchaseRequests,
    ADD BLOCK  PREDICATE Security.fn_tenant_predicate(TenantId) ON dbo.PurchaseRequests AFTER INSERT,
    ADD BLOCK  PREDICATE Security.fn_tenant_predicate(TenantId) ON dbo.PurchaseRequests AFTER UPDATE
    WITH (STATE = ON, SCHEMABINDING = ON);
GO
