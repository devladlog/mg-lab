-- a04-backup.sql
-- SQL Server only. Run on the primary after the seed. The one full backup the database needs before it can join an
-- availability group. A real file, in the instance's default backup folder (never NUL: that would break the log chain).
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @full nvarchar(300) = @bak + N'MGLab_ContosoBikesAG_Full.bak';
BACKUP DATABASE ContosoBikesAG TO DISK = @full WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
GO
SELECT N'Recovery model' AS Item, CONVERT(nvarchar(60), recovery_model_desc) AS Result
FROM sys.databases WHERE name = N'ContosoBikesAG'
UNION ALL
SELECT N'Full backups in msdb', CONVERT(nvarchar(60), COUNT(*))
FROM msdb.dbo.backupset WHERE database_name = N'ContosoBikesAG' AND type = 'D'
UNION ALL
SELECT N'Orders', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesAG.Sales.Orders;
GO
