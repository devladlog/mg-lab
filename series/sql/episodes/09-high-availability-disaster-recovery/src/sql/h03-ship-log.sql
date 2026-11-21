-- h03-ship-log.sql
-- SQL Server only. One log-shipping cycle by hand: back up the primary's log, restore it on the standby WITH STANDBY.
-- (Real log shipping does this with three SQL Server Agent jobs: backup, copy, restore, plus a monitor.)
-- Run after d01 (order 1009). The runner's connection is in master: RESTORE LOG needs exclusive use of the standby.
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @dat nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath'));
IF RIGHT(@dat, 1) <> @sep SET @dat += @sep;
DECLARE @file nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Log1.trn';
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
