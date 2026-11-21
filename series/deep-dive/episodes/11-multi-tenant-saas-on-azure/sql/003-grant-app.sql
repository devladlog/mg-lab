-- Gives the web app's managed identity the least it needs. sqlcmd variable: AppIdentity = the web app's name
-- (the system-assigned identity has the same name as the app). Run as the SQL Entra admin, connected to the database:
--   sqlcmd -S <server>.database.windows.net -d tenants -G -i 003-grant-app.sql -v AppIdentity="app-saas-xxxx"

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(AppIdentity)')
    CREATE USER [$(AppIdentity)] FROM EXTERNAL PROVIDER;
GO
GRANT SELECT, INSERT, UPDATE ON dbo.Tenants TO [$(AppIdentity)];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.PurchaseRequests TO [$(AppIdentity)];
-- The tenant of a row never changes: the app cannot re-label a row even by mistake (the same DENY is in Learn's
-- middle-tier row-level security example). The AFTER UPDATE block predicate is the second lock on the same door.
DENY UPDATE ON dbo.PurchaseRequests (TenantId) TO [$(AppIdentity)];
GO
