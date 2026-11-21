-- Run in the purchase-requests database, signed in as the server's Microsoft Entra admin
-- (Azure portal > SQL database > Query editor, or sqlcmd -G). Run 001-schema.sql first.
-- The web app's system-assigned managed identity has the same name as the web app.
DECLARE @app sysname = N'app-purchreq-CHANGE-ME';   -- the webAppName output of infra/main.bicep
DECLARE @user nvarchar(300) = QUOTENAME(@app);
DECLARE @sql nvarchar(max) = N'';

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @app)
    SET @sql += N'CREATE USER ' + @user + N' FROM EXTERNAL PROVIDER; ';

-- Data rights only. No db_ddladmin: the app can't change the schema, an admin deploys 001-schema.sql.
SET @sql += N'ALTER ROLE db_datareader ADD MEMBER ' + @user + N'; ';
SET @sql += N'ALTER ROLE db_datawriter ADD MEMBER ' + @user + N'; ';
-- The audit trail is append-only, even for the app itself.
SET @sql += N'DENY UPDATE, DELETE ON dbo.AuditEntries TO ' + @user + N'; ';

EXEC sp_executesql @sql;

-- Show what the identity can do (for the recording).
SELECT dp.name AS principal, dp.type_desc, r.name AS role_name
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members rm ON rm.member_principal_id = dp.principal_id
LEFT JOIN sys.database_principals r ON r.principal_id = rm.role_principal_id
WHERE dp.name = @app;

SELECT pr.state_desc, pr.permission_name, OBJECT_NAME(pr.major_id) AS object_name
FROM sys.database_permissions pr
JOIN sys.database_principals dp ON dp.principal_id = pr.grantee_principal_id
WHERE dp.name = @app AND pr.class = 1;
