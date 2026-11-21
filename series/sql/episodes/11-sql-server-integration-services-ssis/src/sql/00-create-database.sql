-- 00-create-database.sql
-- SQL Server only. Run against master on CON-SQL01 (the runner does it after e00-reset.sql).
-- A new throwaway database for episode 11: the same Contoso Bikes order tables as episode 5
-- (01-schema-and-data.sql is a byte-for-byte copy), plus the ETL objects of e01-etl-objects.sql.
USE master;
GO
IF DB_ID(N'ContosoBikesEtl') IS NULL
    CREATE DATABASE ContosoBikesEtl;
GO
