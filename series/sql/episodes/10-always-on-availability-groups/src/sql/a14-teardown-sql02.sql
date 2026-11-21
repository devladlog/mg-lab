-- a14-teardown-sql02.sql
-- SQL Server only. Run on CON-SQL02 after a00-reset.sql (the endpoint is in use while the group exists): drops the
-- endpoint and the login of the other replica's computer account, both created by a03-endpoint-sql02.sql.
USE master;
GO
IF EXISTS (SELECT 1 FROM sys.database_mirroring_endpoints WHERE name = N'Hadr_endpoint')
    DROP ENDPOINT Hadr_endpoint;
GO
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'CONTOSO\CON-SQL01$')
    DROP LOGIN [CONTOSO\CON-SQL01$];
GO
