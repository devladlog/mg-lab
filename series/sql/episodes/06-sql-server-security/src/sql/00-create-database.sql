-- 00-create-database.sql
-- SQL Server only. Run against master as the lab Administrator (episode 6 reuses this database).
-- Compatibility level 160 (SQL Server 2022): scalar UDF inlining needs 150 or higher.
IF DB_ID(N'ContosoBikesApp') IS NULL
    CREATE DATABASE ContosoBikesApp;
GO
ALTER DATABASE ContosoBikesApp SET COMPATIBILITY_LEVEL = 160;
GO
ALTER DATABASE ContosoBikesApp SET RECOVERY SIMPLE;
GO
