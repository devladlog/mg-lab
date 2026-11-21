-- h06-ship-log-fails.sql
-- SQL Server only. Gotcha 2, part 2: the shipping job's next cycle. The new log backup (Log2) starts where the rogue
-- backup ended, not where Log1 ended, so the standby cannot apply it: error 4305, "...which is too recent to apply
-- to the database. An earlier log backup that includes LSN ... can be restored." The RESTORE fails and changes nothing.
-- Run after d03 (order 1011).
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @dat nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath'));
IF RIGHT(@dat, 1) <> @sep SET @dat += @sep;
DECLARE @file nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Log2.trn';
DECLARE @undo nvarchar(300) = @dat + N'MGLab_ContosoBikesHA_Standby.undo';
BACKUP LOG ContosoBikesHA TO DISK = @file WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
RESTORE LOG ContosoBikesHA_Standby FROM DISK = @file WITH STANDBY = @undo, CHECKSUM, STATS = 50;
GO
SELECT N'Orders on the primary' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result FROM ContosoBikesHA.Sales.Orders
UNION ALL
SELECT N'Orders on the standby', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders
UNION ALL
SELECT N'Log backups restored on the standby', CONVERT(nvarchar(60), COUNT(*))
FROM msdb.dbo.restorehistory WHERE destination_database_name = N'ContosoBikesHA_Standby' AND restore_type = 'L';
GO
