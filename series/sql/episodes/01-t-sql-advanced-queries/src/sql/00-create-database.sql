-- 00-create-database.sql
-- SQL Server only (the local DuckDB harness skips this file: it has no databases or compatibility levels).
-- Creates the lab database and makes sure it runs at compatibility level 160 (SQL Server 2022),
-- which the WINDOW clause in q01 requires.
IF DB_ID(N'ContosoLab') IS NULL
    CREATE DATABASE ContosoLab;
GO
ALTER DATABASE ContosoLab SET COMPATIBILITY_LEVEL = 160;
GO
