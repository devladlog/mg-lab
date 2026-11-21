-- a00-reset.sql
-- SQL Server only. Run on BOTH replicas (the runner does secondary first). Removes the availability group and the
-- lab database from this instance, and the database's msdb backup history. The endpoint and its login stay (a14).
-- Dropping the group first matters: a database that belongs to an availability group can't be dropped or set to
-- single-user. On a secondary the database is RESTORING after the group is gone; DROP DATABASE removes it anyway.
-- The backup file (MGLab_ContosoBikesAG_Full.bak) stays on the primary's disk: see demo.md, tear-down.
USE master;
GO
IF EXISTS (SELECT 1 FROM sys.availability_groups WHERE name = N'ag_contoso')
    DROP AVAILABILITY GROUP ag_contoso;
GO
IF DATABASEPROPERTYEX(N'ContosoBikesAG', N'Status') = N'ONLINE'
    ALTER DATABASE ContosoBikesAG SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
GO
DROP DATABASE IF EXISTS ContosoBikesAG;
GO
EXEC msdb.dbo.sp_delete_database_backuphistory @database_name = N'ContosoBikesAG';
GO
