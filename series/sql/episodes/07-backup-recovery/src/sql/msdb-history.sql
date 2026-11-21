-- msdb-history.sql
-- The backup history of the lab database, as the restore planner (src/restore_plan.py) reads it.
-- type: D = full, I = differential, L = log (msdb.dbo.backupset); the file name is in backupmediafamily.
SELECT bs.type, bs.backup_start_date, bs.backup_finish_date, bs.first_lsn, bs.last_lsn, bs.checkpoint_lsn,
       bs.is_copy_only, bmf.physical_device_name
FROM msdb.dbo.backupset AS bs
JOIN msdb.dbo.backupmediafamily AS bmf ON bmf.media_set_id = bs.media_set_id
WHERE bs.database_name = N'ContosoBikesBackup'
ORDER BY bs.backup_start_date, bs.backup_set_id;
