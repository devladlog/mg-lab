-- b00-reset.sql
-- SQL Server only. Removes everything episode 7 creates: both databases and their msdb backup history.
-- The backup FILES stay on the server (SQL Server never deletes them): see demo.md, tear-down.
USE master;
GO
IF DATABASEPROPERTYEX(N'ContosoBikesBackup', N'Status') = N'ONLINE'
    ALTER DATABASE ContosoBikesBackup SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
GO
DROP DATABASE IF EXISTS ContosoBikesBackup;
GO
DROP DATABASE IF EXISTS ContosoBikesRecovered;
GO
EXEC msdb.dbo.sp_delete_database_backuphistory @database_name = N'ContosoBikesBackup';
GO
EXEC msdb.dbo.sp_delete_database_backuphistory @database_name = N'ContosoBikesRecovered';
GO
