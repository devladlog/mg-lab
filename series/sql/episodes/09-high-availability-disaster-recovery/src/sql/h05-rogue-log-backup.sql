-- h05-rogue-log-backup.sql
-- SQL Server only. Gotcha 2, part 1: someone takes an ad hoc log backup of the primary, to a file the shipping job
-- never sees (a tool, a colleague, a second backup job). It is a normal log backup: it moves the log chain forward.
-- Run after d02 (order 1010). The standby has not seen this backup.
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @file nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Rogue.trn';
BACKUP LOG ContosoBikesHA TO DISK = @file WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
GO
SELECT N'Log backups taken on the primary' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result
FROM msdb.dbo.backupset WHERE database_name = N'ContosoBikesHA' AND type = 'L'
UNION ALL
SELECT N'Log backups restored on the standby', CONVERT(nvarchar(60), COUNT(*))
FROM msdb.dbo.restorehistory WHERE destination_database_name = N'ContosoBikesHA_Standby' AND restore_type = 'L';
GO
