-- b02-full-backup.sql
-- SQL Server only. The first full backup: it starts the log chain and is the base of every later differential.
-- CHECKSUM verifies the pages while they are read and stores a checksum for the whole backup;
-- COMPRESSION is supported by Developer edition. Files go to the instance's default backup folder.
USE master;
GO
DECLARE @dir nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@dir, 1) <> CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'))
    SET @dir += CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @file nvarchar(300) = @dir + N'MGLab_ContosoBikesBackup_Full.bak';
BACKUP DATABASE ContosoBikesBackup TO DISK = @file WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
GO
-- b02 result: the backup that was just taken, as msdb recorded it
SELECT TOP (1)
       CASE bs.type WHEN 'D' THEN N'Full' WHEN 'I' THEN N'Differential' WHEN 'L' THEN N'Log' END AS Kind,
       bs.recovery_model AS RecoveryModel,
       CONVERT(int, bs.has_backup_checksums) AS HasBackupChecksums,
       CONVERT(int, bs.is_copy_only) AS IsCopyOnly
FROM msdb.dbo.backupset AS bs
WHERE bs.database_name = N'ContosoBikesBackup'
ORDER BY bs.backup_start_date DESC, bs.backup_set_id DESC;
GO
