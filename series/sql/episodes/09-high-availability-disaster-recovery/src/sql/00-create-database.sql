-- 00-create-database.sql
-- SQL Server only. Run against master on CON-SQL01 (the runner does it after h00-reset.sql).
-- ContosoBikesHA is the PRIMARY of this episode's log-shipping drill: the same Contoso Bikes order tables as
-- episode 5 (01-schema-and-data.sql is a byte-for-byte copy), in the FULL recovery model, because only FULL
-- (or BULK_LOGGED) allows log backups. ContosoBikesHA_Standby is created later, by restoring a backup.
USE master;
GO
IF DB_ID(N'ContosoBikesHA') IS NULL
    CREATE DATABASE ContosoBikesHA;
GO
ALTER DATABASE ContosoBikesHA SET RECOVERY FULL;
GO
