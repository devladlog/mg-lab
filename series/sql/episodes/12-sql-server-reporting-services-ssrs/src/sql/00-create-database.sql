-- 00-create-database.sql
-- SQL Server only. Run against master on CON-SQL01 (the runner does it after r00-reset.sql).
-- A new throwaway database for episode 12: the same Contoso Bikes order tables as episode 5
-- (01-schema-and-data.sql is a byte-for-byte copy) plus the reporting objects of r01-report-objects.sql.
USE master;
GO
IF DB_ID(N'ContosoBikesRpt') IS NULL
    CREATE DATABASE ContosoBikesRpt;
GO
