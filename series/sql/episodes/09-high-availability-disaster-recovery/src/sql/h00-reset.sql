-- h00-reset.sql
-- SQL Server only. Removes everything episode 9 creates: both databases and their msdb backup/restore history.
-- The backup files (MGLab_ContosoBikesHA_*.bak/.trn) and the standby undo file stay on the server: SQL Server
-- never deletes them (see demo.md, tear-down). The next run overwrites the backup files (INIT).
USE master;
GO
IF DATABASEPROPERTYEX(N'ContosoBikesHA', N'Status') = N'ONLINE'
    ALTER DATABASE ContosoBikesHA SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
GO
IF DATABASEPROPERTYEX(N'ContosoBikesHA_Standby', N'Status') = N'ONLINE'
    ALTER DATABASE ContosoBikesHA_Standby SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
GO
DROP DATABASE IF EXISTS ContosoBikesHA;
GO
DROP DATABASE IF EXISTS ContosoBikesHA_Standby;
GO
EXEC msdb.dbo.sp_delete_database_backuphistory @database_name = N'ContosoBikesHA';
GO
EXEC msdb.dbo.sp_delete_database_backuphistory @database_name = N'ContosoBikesHA_Standby';
GO
