-- A read-only SQL login for the gateway data source (SQL authentication; the lab SQL Server is in mixed mode).
-- Run on CON-SQL01 as a sysadmin, in SSMS or with sqlcmd. The password is a sqlcmd variable, never in a file:
--   sqlcmd -S 10.50.0.30 -E -i 01-gateway-login.sql -v GatewayPassword="<typed on the day>"
-- The database ContosoBikesDW comes from episode 11 (its scripts 01, 02 and 03).
USE [master];
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'pbi_gateway_reader')
    CREATE LOGIN [pbi_gateway_reader] WITH PASSWORD = N'$(GatewayPassword)', CHECK_POLICY = ON, DEFAULT_DATABASE = [ContosoBikesDW];
GO
USE [ContosoBikesDW];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'pbi_gateway_reader')
    CREATE USER [pbi_gateway_reader] FOR LOGIN [pbi_gateway_reader];
GO
ALTER ROLE [db_datareader] ADD MEMBER [pbi_gateway_reader];
GO
