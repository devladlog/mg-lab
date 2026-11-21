-- Removes what 01-gateway-login.sql created. Run on CON-SQL01 as a sysadmin. ContosoBikesDW itself belongs to episode 11.
USE [ContosoBikesDW];
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'pbi_gateway_reader')
    DROP USER [pbi_gateway_reader];
GO
USE [master];
GO
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'pbi_gateway_reader')
    DROP LOGIN [pbi_gateway_reader];
GO
