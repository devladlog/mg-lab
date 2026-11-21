-- h08-failover.sql
-- SQL Server only. The failover drill. Run after d04 (order 1012, committed after the last shipped log).
-- 1. Tail-log backup of the primary WITH NORECOVERY: it captures the log that was never backed up (order 1012)
--    and leaves the primary in the RESTORING state, so nobody can write to it any more.
-- 2. Restore that tail on the standby WITH RECOVERY: the standby becomes a normal, writable, ONLINE database.
-- Nothing is lost because the tail was taken from a primary that was still running. If the primary were dead you would
-- restore the last shipped log WITH RECOVERY and accept losing whatever was not shipped (that is the RPO).
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @tail nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Tail.trn';
BACKUP LOG ContosoBikesHA TO DISK = @tail WITH NORECOVERY, INIT, CHECKSUM, COMPRESSION, STATS = 50;
RESTORE LOG ContosoBikesHA_Standby FROM DISK = @tail WITH RECOVERY, CHECKSUM, STATS = 50;
GO
SELECT N'Old primary state' AS Item, CONVERT(nvarchar(60), state_desc) AS Result
FROM sys.databases WHERE name = N'ContosoBikesHA'
UNION ALL
SELECT N'Promoted copy state', CONVERT(nvarchar(60), CONCAT(state_desc, CASE WHEN is_in_standby = 1 THEN N' (read-only standby)' ELSE N'' END))
FROM sys.databases WHERE name = N'ContosoBikesHA_Standby'
UNION ALL
SELECT N'Orders on the promoted copy', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders
UNION ALL
SELECT N'Order 1012 on the promoted copy', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders WHERE OrderId = 1012;
GO
