-- h07-repair-chain.sql
-- SQL Server only. The fix for error 4305: restore the log backup the standby is missing (the rogue one) first, then the
-- one that failed. Nothing is re-initialised; the chain is simply applied in order, every restore WITH STANDBY.
-- msdb's backup history on the primary (type L, ordered by first_lsn) is how you find the missing file in real life.
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @dat nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath'));
IF RIGHT(@dat, 1) <> @sep SET @dat += @sep;
DECLARE @rogue nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Rogue.trn';
DECLARE @next nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Log2.trn';
DECLARE @undo nvarchar(300) = @dat + N'MGLab_ContosoBikesHA_Standby.undo';
RESTORE LOG ContosoBikesHA_Standby FROM DISK = @rogue WITH STANDBY = @undo, CHECKSUM, STATS = 50;
RESTORE LOG ContosoBikesHA_Standby FROM DISK = @next WITH STANDBY = @undo, CHECKSUM, STATS = 50;
GO
SELECT N'Orders on the primary' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result FROM ContosoBikesHA.Sales.Orders
UNION ALL
SELECT N'Orders on the standby', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders
UNION ALL
SELECT N'Log backups restored on the standby', CONVERT(nvarchar(60), COUNT(*))
FROM msdb.dbo.restorehistory WHERE destination_database_name = N'ContosoBikesHA_Standby' AND restore_type = 'L';
GO
