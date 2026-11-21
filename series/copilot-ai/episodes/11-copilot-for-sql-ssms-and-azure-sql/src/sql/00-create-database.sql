-- 00-create-database.sql
-- SQL Server only (CON-SQL01). Run against master as the lab Administrator:
--   sqlcmd -S 10.50.0.30 -E -i 00-create-database.sql -v AnalystPassword="<typed off camera>"
-- On Azure SQL Database skip this file: create the database in the portal (see demo.md) and a contained user instead.
-- The password is a sqlcmd variable on purpose: nothing secret is stored in the repository.
IF DB_ID(N'ContosoCopilot') IS NULL
    CREATE DATABASE ContosoCopilot;
GO
ALTER DATABASE ContosoCopilot SET COMPATIBILITY_LEVEL = 160;   -- SQL Server 2022
GO
-- A normal developer-style login: it can read and write the demo database. It is NOT sysadmin.
IF SUSER_ID(N'copilot_demo_analyst') IS NULL
    CREATE LOGIN copilot_demo_analyst WITH PASSWORD = N'$(AnalystPassword)', CHECK_POLICY = ON, DEFAULT_DATABASE = ContosoCopilot;
GO
