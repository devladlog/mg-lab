-- r00-reset.sql
-- SQL Server only. Run against master on CON-SQL01. Drops episode 12's throwaway database and its SQL login (safe to re-run).
USE master;
GO
IF DB_ID(N'ContosoBikesRpt') IS NOT NULL
BEGIN
    ALTER DATABASE ContosoBikesRpt SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE ContosoBikesRpt;
END
GO
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'rs_reader')
    DROP LOGIN rs_reader;
GO
