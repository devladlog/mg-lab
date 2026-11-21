-- h01-rpo-exposure.sql
-- SQL Server only. How many minutes of data would be lost if a database died right now? For every user database:
-- the newest full, differential and log backup in msdb, and the minutes since the newest of them that counts.
-- A log backup only counts when the database is not in SIMPLE recovery (SIMPLE has no log backups). GREATEST
-- ignores NULLs (SQL Server 2022, compatibility level 160); it is NULL only when nothing was ever backed up.
-- The runner (and src/dr_report.py) compare MinutesAtRisk with the RPO target.
USE master;
GO
SELECT d.name                          AS DatabaseName,
       d.recovery_model_desc           AS RecoveryModel,
       d.state_desc                    AS State,
       CONVERT(int, d.is_in_standby)   AS IsStandby,
       b.LastFull,
       b.LastDiff,
       b.LastLog,
       DATEDIFF(MINUTE,
                GREATEST(b.LastFull, b.LastDiff, CASE WHEN d.recovery_model_desc <> N'SIMPLE' THEN b.LastLog END),
                GETDATE())             AS MinutesAtRisk
FROM sys.databases AS d
OUTER APPLY (SELECT MAX(CASE WHEN bs.type = 'D' THEN bs.backup_finish_date END) AS LastFull,
                    MAX(CASE WHEN bs.type = 'I' THEN bs.backup_finish_date END) AS LastDiff,
                    MAX(CASE WHEN bs.type = 'L' THEN bs.backup_finish_date END) AS LastLog
             FROM msdb.dbo.backupset AS bs
             WHERE bs.database_name = d.name) AS b
WHERE d.database_id > 4
ORDER BY d.name;
GO
