-- Run in the Azure SQL database (Query editor, signed in as the Microsoft Entra admin) AFTER
-- sqlserver-migrations.sql. deploy-azure.sh writes out/grant-app-identity.sql with the app name filled in.
--
-- The web app's system-assigned managed identity gets read/write on the data only. No db_ddladmin:
-- the schema is changed by the deployment identity (you, running the reviewed script), not by the app.
CREATE USER [__APP_NAME__] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [__APP_NAME__];
ALTER ROLE db_datawriter ADD MEMBER [__APP_NAME__];
GO

-- Check: the user exists and which roles it has.
SELECT u.name AS [user], r.name AS [role]
FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = N'__APP_NAME__';
