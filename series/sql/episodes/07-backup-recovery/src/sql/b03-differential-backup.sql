-- b03-differential-backup.sql
-- SQL Server only. A differential backup holds the extents changed since the last full backup (its base).
-- To restore it you restore the base first, then only the most recent differential.
USE master;
GO
DECLARE @dir nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@dir, 1) <> CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'))
    SET @dir += CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @file nvarchar(300) = @dir + N'MGLab_ContosoBikesBackup_Diff.bak';
BACKUP DATABASE ContosoBikesBackup TO DISK = @file WITH DIFFERENTIAL, INIT, CHECKSUM, COMPRESSION, STATS = 50;
GO
-- b03 result: the backup that was just taken, as msdb recorded it
SELECT TOP (1)
       CASE bs.type WHEN 'D' THEN N'Full' WHEN 'I' THEN N'Differential' WHEN 'L' THEN N'Log' END AS Kind,
       bs.recovery_model AS RecoveryModel,
       CONVERT(int, bs.has_backup_checksums) AS HasBackupChecksums,
       CONVERT(int, bs.is_copy_only) AS IsCopyOnly
FROM msdb.dbo.backupset AS bs
WHERE bs.database_name = N'ContosoBikesBackup'
ORDER BY bs.backup_start_date DESC, bs.backup_set_id DESC;
GO
