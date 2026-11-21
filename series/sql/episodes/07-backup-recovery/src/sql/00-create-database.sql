-- 00-create-database.sql
-- SQL Server only. Run against master on CON-SQL01 (the runner does it after b00-reset.sql).
-- A new throwaway database for episode 7: the same Contoso Bikes order tables as episode 5
-- (01-schema-and-data.sql is a byte-for-byte copy), but in the FULL recovery model, because
-- only FULL (or BULK_LOGGED) allows log backups and point-in-time restore.
-- Episode 5's ContosoBikesApp stays in SIMPLE recovery and is not touched.
USE master;
GO
IF DB_ID(N'ContosoBikesBackup') IS NULL
    CREATE DATABASE ContosoBikesBackup;
GO
ALTER DATABASE ContosoBikesBackup SET RECOVERY FULL;
GO
