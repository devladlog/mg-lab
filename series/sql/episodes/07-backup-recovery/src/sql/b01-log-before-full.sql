-- b01-log-before-full.sql
-- SQL Server only. The gotcha first: the database is in FULL recovery, but nothing has been backed up yet.
-- A log backup is refused (error 4214, "no current database backup"): FULL recovery only starts to
-- protect you after the first full backup. This batch is EXPECTED to fail; the runner checks the message.
USE master;
GO
DECLARE @dir nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@dir, 1) <> CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'))
    SET @dir += CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @file nvarchar(300) = @dir + N'MGLab_ContosoBikesBackup_Log0.trn';
BACKUP LOG ContosoBikesBackup TO DISK = @file WITH INIT, CHECKSUM;
GO
