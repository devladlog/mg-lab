-- 00-create-database.sql
-- SQL Server only (the local DuckDB harness skips this file: it has no databases, compatibility levels or Query Store).
-- Run it against master on CON-SQL01. Creates the lab database used by episodes 3 and 4 of DEVLADLOG SQL.
--   * compatibility level 160 (SQL Server 2022): GENERATE_SERIES in 01-schema-and-data.sql needs it
--   * SIMPLE recovery: the data load is ~100 MB and this is a lab, not production
--   * Query Store ON with QUERY_CAPTURE_MODE = ALL, so every lab query is captured (episode 4 reads it)
IF DB_ID(N'ContosoBikesPerf') IS NULL
    CREATE DATABASE ContosoBikesPerf;
GO
ALTER DATABASE ContosoBikesPerf SET COMPATIBILITY_LEVEL = 160;
GO
ALTER DATABASE ContosoBikesPerf SET RECOVERY SIMPLE;
GO
ALTER DATABASE ContosoBikesPerf SET QUERY_STORE = ON (OPERATION_MODE = READ_WRITE, QUERY_CAPTURE_MODE = ALL);
GO
